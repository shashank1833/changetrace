from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from changetrace_schemas import Component, ComponentType, Evidence, EvidenceType, SourceLocation

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

    Tree-sitter can be added as an optional parser without changing this output contract.
    """

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
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                index.parse_warnings.append(f"Skipped {path}: {exc}")
                continue
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
                if decorators & {
                    "router.get",
                    "router.post",
                    "router.put",
                    "router.patch",
                    "router.delete",
                    "app.get",
                    "app.post",
                }:
                    kind = ComponentType.API
                elif decorators & {"task", "shared_task", "celery.task", "scheduler.scheduled_job", "cron"} or any(
                    x in node.name.lower() for x in ("worker", "job", "cron")
                ):
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
            (r"(?:export\s+)?class\s+(\w+)", ComponentType.CLASS, "JavaScript/TypeScript class"),
            (r"(?:describe|it|test)\s*\(\s*['\"]([^'\"]+)", ComponentType.TEST, "JavaScript/TypeScript test"),
            (r"(?:router|app)\.(?:get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)", ComponentType.API, "HTTP route"),
            (r"(?:fetch|axios\.(?:get|post|put|patch|delete))\s*\(", ComponentType.INTEGRATION, "External HTTP call"),
        ]
        for pattern, kind, reason in patterns:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                name = match.group(1) if match.lastindex else match.group(0).split("(")[0]
                self._add(index, file, line, line, name, kind, reason)
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
