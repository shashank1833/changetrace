from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from changetrace_schemas import Component, ComponentType, Evidence, EvidenceType, SourceLocation

from services.repository_analysis.sandbox import ParserSandbox, SandboxViolationError
from services.repository_analysis.treesitter_parser import TreeSitterParser

SUPPORTED_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".md"}
IGNORED_PARTS = {".git", "node_modules", ".venv", "venv", "dist", "build", "coverage", "__pycache__"}


@dataclass
class IndexedRepository:
    root: Path
    snapshot_id: str
    commit_sha: str
    repository_id: str = "unknown"
    components: list[Component] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    imports: list[tuple[str, str, str]] = field(default_factory=list)
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    references: dict[str, set[str]] = field(default_factory=dict)
    parse_warnings: list[str] = field(default_factory=list)
    file_text: dict[str, str] = field(default_factory=dict)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _id(prefix: str, *parts: object) -> str:
    raw = ":".join(str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"  # noqa: S324


def _evidence_type(component_type: ComponentType) -> EvidenceType:
    return {
        ComponentType.TEST: EvidenceType.TEST_REFERENCE,
        ComponentType.API: EvidenceType.API_REFERENCE,
        ComponentType.DATABASE: EvidenceType.DB_REFERENCE,
        ComponentType.BUSINESS_RULE: EvidenceType.BUSINESS_RULE,
    }.get(component_type, EvidenceType.CODE_REFERENCE)


class RepositoryAnalyzer:
    """Deterministic source indexer. Python uses stdlib AST; JS/TS use conservative patterns.

    Tree-sitter is integrated as an optional parser when available.
    """

    def __init__(self, use_treesitter: bool = True, sandbox: ParserSandbox | None = None) -> None:
        self.use_treesitter = use_treesitter
        self.treesitter = TreeSitterParser() if use_treesitter else None
        self.sandbox = sandbox or ParserSandbox()

    def scan(self, root: Path, snapshot_id: str, commit_sha: str, repository_id: str = "unknown") -> IndexedRepository:
        root = root.resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Repository path does not exist: {root}")
        index = IndexedRepository(
            root=root,
            snapshot_id=snapshot_id,
            commit_sha=commit_sha,
            repository_id=repository_id,
        )
        self.sandbox.apply_process_limits()
        total_bytes = 0
        file_count = 0
        import os
        paths: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted([d for d in dirnames if d not in IGNORED_PARTS and not d.startswith(".")])
            for filename in filenames:
                paths.append(Path(dirpath) / filename)
        paths.sort()
        for path in paths:
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                self.sandbox.validate_path(path, root)
                file_size = self.sandbox.check_file_size(path)
            except SandboxViolationError as exc:
                index.parse_warnings.append(f"Sandbox limit exceeded for {path}: {exc}")
                continue

            if file_count >= self.sandbox.limits.max_files_count:
                max_fc = self.sandbox.limits.max_files_count
                index.parse_warnings.append(f"Reached max file scan count limit ({max_fc})")
                break
            if total_bytes + file_size > self.sandbox.limits.max_total_bytes:
                max_tb = self.sandbox.limits.max_total_bytes
                index.parse_warnings.append(f"Reached max repository size limit ({max_tb} bytes)")
                break

            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                index.parse_warnings.append(f"Skipped {path}: {exc}")
                continue

            total_bytes += file_size
            file_count += 1
            relative = path.relative_to(root).as_posix()
            index.file_text[relative] = text
            self._add(
                index,
                relative,
                1,
                max(1, len(text.splitlines())),
                relative,
                ComponentType.FILE,
                "Source file in repository snapshot",
            )
            if path.suffix == ".py":
                self._parse_python(index, relative, text)
            elif path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
                self._parse_javascript(index, relative, text)
            elif path.suffix == ".sql":
                self._parse_sql(index, relative, text)
            elif path.suffix == ".md":
                self._add(
                    index,
                    relative,
                    1,
                    max(1, len(text.splitlines())),
                    relative,
                    ComponentType.DOCUMENT,
                    "Repository documentation",
                )
            self._index_terms(index, relative, text)
        return index

    def _add(
        self, index: IndexedRepository, file: str, start: int, end: int, name: str, kind: ComponentType, reason: str
    ) -> Component:
        lines = index.file_text[file].splitlines()
        snippet = "\n".join(lines[max(0, start - 1) : end])[:4000]
        evidence_id = _id("E", index.snapshot_id, file, start, end, name)
        evidence = Evidence(
            id=evidence_id,
            type=_evidence_type(kind),
            repository_snapshot_id=index.snapshot_id,
            repository_id=index.repository_id,
            commit_sha=index.commit_sha,
            location=SourceLocation(file=file, line_start=start, line_end=max(start, end), symbol=name),
            content_hash=content_hash(snippet),
            reason=reason,
            snippet=snippet,
        )
        component = Component(
            id=_id("C", file, start, name),
            type=kind,
            name=name,
            location=evidence.location,
            reason=reason,
            evidence_ids=[evidence_id],
        )
        index.evidence.append(evidence)
        index.components.append(component)
        return component

    def _parse_python(self, index: IndexedRepository, file: str, text: str) -> None:
        try:
            tree = ast.parse(text, filename=file)
        except SyntaxError as exc:
            index.parse_warnings.append(f"Python parse failure {file}:{exc.lineno}: {exc.msg}")
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = (
                    ComponentType.TEST
                    if node.name.startswith("test_") or "/tests/" in f"/{file}"
                    else ComponentType.FUNCTION
                )
                decorators = {self._name(d) for d in node.decorator_list}
                is_api_route = any(
                    any(d.endswith(f".{verb}") for verb in ("get", "post", "put", "patch", "delete", "route", "api_route"))
                    or "router." in d or "app." in d or "blueprint." in d or "bp." in d
                    for d in decorators
                )
                is_background_job = (
                    bool(decorators & {"task", "shared_task", "celery.task", "scheduler.scheduled_job", "cron"})
                    or any(part in file.lower().replace("\\", "/").split("/") for part in ("jobs", "workers", "tasks", "cron"))
                    or any(x in node.name.lower() for x in ("worker", "cron_job", "background_task", "celery_task"))
                )
                if is_api_route:
                    kind = ComponentType.API
                elif is_background_job:
                    kind = ComponentType.JOB
                self._add(
                    index,
                    file,
                    node.lineno,
                    getattr(node, "end_lineno", node.lineno),
                    node.name,
                    kind,
                    f"Detected Python {kind.value.lower().replace('_', ' ')}",
                )
                for called in self._calls(node):
                    index.calls.append((node.name, called, file))
            elif isinstance(node, ast.ClassDef):
                bases = {self._name(base).lower() for base in node.bases}
                kind = ComponentType.DATABASE if bases & {"base", "model", "declarativebase"} else ComponentType.CLASS
                self._add(
                    index,
                    file,
                    node.lineno,
                    getattr(node, "end_lineno", node.lineno),
                    node.name,
                    kind,
                    f"Detected Python {kind.value.lower()}",
                )
                if any(base.endswith("enum") for base in bases):
                    for statement in node.body:
                        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                            target = statement.targets[0] if isinstance(statement, ast.Assign) else statement.target
                            if isinstance(target, ast.Name) and target.id.isupper():
                                self._add(
                                    index,
                                    file,
                                    statement.lineno,
                                    getattr(statement, "end_lineno", statement.lineno),
                                    f"{node.name}.{target.id}",
                                    ComponentType.STATE,
                                    f"State value in {node.name}",
                                )
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                module = node.module if isinstance(node, ast.ImportFrom) else ""
                for name in names:
                    index.imports.append((file, f"{module}.{name}".strip("."), str(node.lineno)))
            elif isinstance(node, ast.If):
                condition = ast.get_source_segment(text, node.test) or ""
                if any(
                    token in condition.lower() for token in ("status", "role", "permission", "eligible", "inspection")
                ):
                    self._add(
                        index,
                        file,
                        node.lineno,
                        getattr(node.test, "end_lineno", node.lineno),
                        f"rule:{condition[:80]}",
                        ComponentType.BUSINESS_RULE,
                        "Conditional business logic detected",
                    )
            elif isinstance(node, ast.Call):
                called = self._name(node.func).lower()
                if called in {"requests.get", "requests.post", "httpx.get", "httpx.post", "client.get", "client.post"}:
                    self._add(
                        index,
                        file,
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno),
                        self._name(node.func),
                        ComponentType.INTEGRATION,
                        "External HTTP call detected",
                    )

    def _parse_javascript(self, index: IndexedRepository, file: str, text: str) -> None:
        patterns = [
            (r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", ComponentType.FUNCTION, "JavaScript/TypeScript function"),
            (r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_]+)\s*=>", ComponentType.FUNCTION, "JavaScript/TypeScript function"),
            (r"(?:export\s+)?class\s+(\w+)", ComponentType.CLASS, "JavaScript/TypeScript class"),
            (r"(?:describe|it|test)\s*\(\s*['\"]([^'\"]+)", ComponentType.TEST, "JavaScript/TypeScript test"),
            (r"(?:router|app)\.(?:get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)", ComponentType.API, "HTTP route"),
            (r"(?:fetch|axios\.(?:get|post|put|patch|delete))\s*\(", ComponentType.INTEGRATION, "External HTTP call"),
            (r"(?:export\s+)?enum\s+(\w+)", ComponentType.CLASS, "JavaScript/TypeScript enum"),
        ]
        for pattern, kind, reason in patterns:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                name = match.group(1) if match.lastindex else match.group(0).split("(")[0]
                self._add(index, file, line, line, name, kind, reason)
        # Parse TypeScript type aliases and enums
        for match in re.finditer(r"(?:export\s+)?type\s+([A-Za-z0-9_]+)\s*=\s*([^;\n]+)", text):
            line = text.count("\n", 0, match.start()) + 1
            type_name = match.group(1)
            self._add(
                index, file, line, line, type_name, ComponentType.CLASS, f"TypeScript type definition: {type_name}"
            )
        for match in re.finditer(r"(?:import[^'\"]+from\s+|require\s*\()['\"]([^'\"]+)", text):
            index.imports.append((file, match.group(1), str(text.count("\n", 0, match.start()) + 1)))
        for match in re.finditer(r"\b(\w+)\s*\(", text):
            index.calls.append((file, match.group(1), file))

    def _parse_sql(self, index: IndexedRepository, file: str, text: str) -> None:
        for match in re.finditer(r"\b(?:CREATE\s+TABLE|FROM|JOIN|UPDATE|INTO)\s+([\w.]+)", text, re.I):
            line = text.count("\n", 0, match.start()) + 1
            self._add(index, file, line, line, match.group(1), ComponentType.DATABASE, "SQL database entity reference")

    def _index_terms(self, index: IndexedRepository, file: str, text: str) -> None:
        for term in set(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text.lower())):
            index.references.setdefault(term, set()).add(file)

    @staticmethod
    def _name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = RepositoryAnalyzer._name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        if isinstance(node, ast.Call):
            return RepositoryAnalyzer._name(node.func)
        return ""

    @classmethod
    def _calls(cls, node: ast.AST) -> set[str]:
        return {cls._name(item.func) for item in ast.walk(node) if isinstance(item, ast.Call) and cls._name(item.func)}
