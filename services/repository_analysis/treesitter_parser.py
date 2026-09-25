from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("changetrace.treesitter")

_TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None
_LANGUAGE_PACK_AVAILABLE = importlib.util.find_spec("tree_sitter_language_pack") is not None


@dataclass
class ParsedSymbol:
    name: str
    kind: str  # function, class, route, state, import, call, sql_operation, transition
    line_start: int
    line_end: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TreeSitterMetrics:
    total_files_attempted: int = 0
    successful_parses: int = 0
    fallback_parses: int = 0
    parse_errors: list[str] = field(default_factory=list)
    symbols_extracted_by_kind: dict[str, int] = field(default_factory=dict)

    def record_symbol(self, kind: str) -> None:
        self.symbols_extracted_by_kind[kind] = self.symbols_extracted_by_kind.get(kind, 0) + 1


class TreeSitterParser:
    """Comprehensive Tree-sitter parser with route, call, import, SQL, and state extraction.

    Provides robust regex fallback when tree-sitter or language grammars are missing.
    """

    def __init__(self) -> None:
        self.available = _TREE_SITTER_AVAILABLE and _LANGUAGE_PACK_AVAILABLE
        self._parsers: dict[str, Any] = {}
        self.metrics = TreeSitterMetrics()

    def is_available(self) -> bool:
        return self.available

    def get_parser(self, language: str) -> Any | None:
        if not self.available:
            return None
        if language in self._parsers:
            return self._parsers[language]
        try:
            import tree_sitter_language_pack as tslp  # type: ignore
            parser = tslp.get_parser(language)
            self._parsers[language] = parser
            return parser
        except Exception as exc:
            logger.debug("Tree-sitter parser initialization failed for %s: %s", language, exc)
            return None

    def extract_symbols(self, text: str, language: str, file_path: str = "") -> list[ParsedSymbol]:
        """Extract structured symbols using tree-sitter when available, falling back to regex analysis."""
        self.metrics.total_files_attempted += 1
        parser = self.get_parser(language)

        if not parser:
            self.metrics.fallback_parses += 1
            symbols = self._fallback_extract(text, language, file_path)
            for s in symbols:
                self.metrics.record_symbol(s.kind)
            return symbols

        try:
            tree = parser.parse(text.encode("utf-8"))
            root = tree.root_node
            if root.has_error:
                self.metrics.parse_errors.append(f"Syntax error in {file_path or language}")

            symbols = []
            self._walk_node(root, symbols, language, text)

            # If tree-sitter returned empty for a non-trivial file, supplement with pattern extraction
            if not symbols and len(text.strip()) > 20:
                self.metrics.fallback_parses += 1
                fallback_syms = self._fallback_extract(text, language, file_path)
                symbols.extend(fallback_syms)
            else:
                self.metrics.successful_parses += 1

            for s in symbols:
                self.metrics.record_symbol(s.kind)

            return symbols
        except Exception as exc:
            logger.warning("Tree-sitter parsing failed for %s: %s", language, exc)
            self.metrics.fallback_parses += 1
            self.metrics.parse_errors.append(str(exc))
            return self._fallback_extract(text, language, file_path)

    def _walk_node(self, node: Any, symbols: list[ParsedSymbol], language: str, source_text: str) -> None:
        node_type = node.type

        # 1. Functions & Methods
        if node_type in {
            "function_definition", "async_function_definition",
            "function_declaration", "method_definition",
        }:
            name = self._get_node_name(node)
            if name:
                side_effects = self._detect_node_side_effects(node, source_text)
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="function",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        details={"side_effects": side_effects} if side_effects else {},
                    )
                )

        # 2. Variable declarator holding arrow functions (TypeScript / JavaScript)
        elif node_type in {"variable_declarator", "lexical_declaration"}:
            name, arrow_node = self._find_arrow_function_declarator(node)
            if name and arrow_node:
                side_effects = self._detect_node_side_effects(arrow_node, source_text)
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="function",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        details={"type": "arrow_function", "side_effects": side_effects},
                    )
                )

        # 3. Classes
        elif node_type in {"class_definition", "class_declaration"}:
            name = self._get_node_name(node)
            if name:
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="class",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    )
                )

        # 4. TypeScript type aliases, union states, and enums
        elif node_type in {"type_alias_declaration", "enum_declaration"}:
            name = self._get_node_name(node)
            if name:
                is_state = any(k in name.lower() for k in ("status", "state", "phase", "step"))
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="state" if is_state else "class",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        details={"is_state_enum": is_state},
                    )
                )

        # 5. Route Definitions (Express / Fastify / Next.js / FastAPI / Flask)
        elif node_type in {"call_expression", "decorator"}:
            route_info = self._extract_route(node, source_text)
            if route_info:
                symbols.append(
                    ParsedSymbol(
                        name=f"{route_info['method']} {route_info['path']}",
                        kind="route",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        details=route_info,
                    )
                )

        # 6. Call Expressions
        elif node_type in {"call_expression", "call"}:
            callee = self._extract_callee_name(node)
            if callee and not callee.startswith(("console.", "print", "logger.", "logging.")):
                symbols.append(
                    ParsedSymbol(
                        name=callee,
                        kind="call",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    )
                )

        # 7. Import Statements
        elif node_type in {"import_statement", "import_from_statement"}:
            imported = self._extract_import_info(node, source_text)
            if imported:
                symbols.append(
                    ParsedSymbol(
                        name=imported["module"],
                        kind="import",
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        details=imported,
                    )
                )

        for child in node.children:
            self._walk_node(child, symbols, language, source_text)

    def _get_node_name(self, node: Any) -> str | None:
        for child in node.children:
            if child.type in {"identifier", "property_identifier", "type_identifier"}:
                return child.text.decode("utf-8")
        return None

    def _find_arrow_function_declarator(self, node: Any) -> tuple[str | None, Any | None]:
        if node.type == "variable_declarator":
            name = None
            arrow = None
            for child in node.children:
                if child.type == "identifier":
                    name = child.text.decode("utf-8")
                elif child.type in {"arrow_function", "function_expression"}:
                    arrow = child
            if name and arrow:
                return name, arrow
        return None, None

    def _extract_route(self, node: Any, source_text: str) -> dict[str, Any] | None:
        try:
            node_text = node.text.decode("utf-8")
        except Exception:
            return None

        # Python route decorators: @app.get("/path"), @router.post("/path")
        py_match = re.search(
            r"@(app|router|api)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
            node_text,
            re.IGNORECASE,
        )
        if py_match:
            return {
                "framework": "fastapi",
                "method": py_match.group(2).upper(),
                "path": py_match.group(3),
            }

        # JS/TS routes: app.get('/path', ...), router.post('/path', ...)
        js_match = re.search(
            r"\b(app|router|server|fastify)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
            node_text,
            re.IGNORECASE,
        )
        if js_match:
            return {
                "framework": "express",
                "method": js_match.group(2).upper(),
                "path": js_match.group(3),
            }
        return None

    def _extract_callee_name(self, node: Any) -> str | None:
        for child in node.children:
            if child.type in {"identifier", "member_expression", "attribute"}:
                try:
                    return child.text.decode("utf-8")
                except Exception:
                    pass
        return None

    def _extract_import_info(self, node: Any, source_text: str) -> dict[str, Any] | None:
        try:
            text = node.text.decode("utf-8")
        except Exception:
            return None

        # JS/TS: import { x, y } from './module'
        ts_match = re.search(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", text)
        if ts_match:
            return {"module": ts_match.group(1)}

        # Python: from x import y
        py_match = re.search(r"from\s+([a-zA-Z0-9_\.]+)\s+import", text)
        if py_match:
            return {"module": py_match.group(1)}

        # Python: import x
        py_imp = re.search(r"import\s+([a-zA-Z0-9_\.]+)", text)
        if py_imp:
            return {"module": py_imp.group(1)}

        return None

    def _detect_node_side_effects(self, node: Any, source_text: str) -> list[str]:
        try:
            text = node.text.decode("utf-8")
        except Exception:
            return []

        effects = []
        if re.search(r"\b(commit|save|insert|update|delete|execute)\b", text, re.IGNORECASE):
            effects.append("db_mutation")
        if re.search(r"\b(fetch|axios|httpx|http|request|send)\b", text, re.IGNORECASE):
            effects.append("http_call")
        if re.search(r"\b(status|state)\s*=\s*", text, re.IGNORECASE):
            effects.append("state_assignment")
        return effects

    def _detect_text_side_effects(self, text: str) -> list[str]:
        effects = []
        if re.search(r"\b(commit|save|insert|update|delete|execute)\b", text, re.IGNORECASE):
            effects.append("db_mutation")
        if re.search(r"\b(fetch|axios|httpx|http|request|send)\b", text, re.IGNORECASE):
            effects.append("http_call")
        if re.search(r"\b(status|state)\s*=\s*", text, re.IGNORECASE):
            effects.append("state_assignment")
        return effects

    def _fallback_extract(self, text: str, language: str, file_path: str = "") -> list[ParsedSymbol]:
        """Robust pattern-based extraction when Tree-sitter is unavailable or encounters syntax errors."""
        symbols: list[ParsedSymbol] = []
        lines = text.splitlines()

        # SQL extraction
        if language == "sql" or file_path.endswith(".sql"):
            for idx, line in enumerate(lines, 1):
                match = re.search(
                    r"\b(CREATE\s+TABLE|ALTER\s+TABLE|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-zA-Z0-9_]+)",
                    line,
                    re.IGNORECASE,
                )
                if match:
                    op, tbl = match.group(1).upper(), match.group(2)
                    symbols.append(
                        ParsedSymbol(
                            name=f"{op} {tbl}",
                            kind="sql_operation",
                            line_start=idx,
                            line_end=idx,
                            details={"operation": op, "table": tbl},
                        )
                    )
            return symbols

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()

            # Routes
            route_match = re.search(
                r"@(app|router|api)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
                stripped,
                re.IGNORECASE,
            )
            if route_match:
                method, path = route_match.group(2).upper(), route_match.group(3)
                symbols.append(
                    ParsedSymbol(
                        name=f"{method} {path}",
                        kind="route",
                        line_start=idx,
                        line_end=idx,
                        details={"method": method, "path": path},
                    )
                )
                continue

            # Functions (Python)
            fn_match = re.match(r"^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(", stripped)
            if fn_match:
                name = fn_match.group(1)
                snippet_window = "\n".join(lines[idx - 1 : min(len(lines), idx + 20)])
                side_effects = self._detect_text_side_effects(snippet_window)
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="function",
                        line_start=idx,
                        line_end=idx + 5,
                        details={"side_effects": side_effects} if side_effects else {},
                    )
                )
                continue

            # Functions & Arrow Functions (JS/TS)
            js_fn = re.match(r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)\s*\(", stripped)
            if js_fn:
                name = js_fn.group(1)
                snippet_window = "\n".join(lines[idx - 1 : min(len(lines), idx + 20)])
                side_effects = self._detect_text_side_effects(snippet_window)
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="function",
                        line_start=idx,
                        line_end=idx + 5,
                        details={"side_effects": side_effects} if side_effects else {},
                    )
                )
                continue

            arrow_match = re.match(
                r"^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
                stripped,
            )
            if arrow_match:
                name = arrow_match.group(1)
                snippet_window = "\n".join(lines[idx - 1 : min(len(lines), idx + 20)])
                side_effects = self._detect_text_side_effects(snippet_window)
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind="function",
                        line_start=idx,
                        line_end=idx + 5,
                        details={"type": "arrow_function", "side_effects": side_effects},
                    )
                )
                continue

            # Classes (Python / TS)
            cls_match = re.match(r"^(?:export\s+)?class\s+([a-zA-Z0-9_]+)", stripped)
            if cls_match:
                symbols.append(
                    ParsedSymbol(
                        name=cls_match.group(1),
                        kind="class",
                        line_start=idx,
                        line_end=idx + 10,
                    )
                )
                continue

            # Enums / Types
            type_match = re.match(r"^(?:export\s+)?(?:enum|type)\s+([a-zA-Z0-9_]+)", stripped)
            if type_match:
                tname = type_match.group(1)
                is_st = any(k in tname.lower() for k in ("state", "status", "phase", "step"))
                symbols.append(
                    ParsedSymbol(
                        name=tname,
                        kind="state" if is_st else "class",
                        line_start=idx,
                        line_end=idx + 5,
                    )
                )
                continue

            # Imports
            if stripped.startswith("import ") or stripped.startswith("from "):
                symbols.append(
                    ParsedSymbol(
                        name=stripped[:50],
                        kind="import",
                        line_start=idx,
                        line_end=idx,
                    )
                )

        return symbols
