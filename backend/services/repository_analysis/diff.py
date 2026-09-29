from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from changetrace_schemas import (
    ChangeKind,
    ChangeSet,
    ComponentType,
    DiffChange,
    GraphDelta,
    LineChange,
    SourceLocation,
    StateValueChange,
    SymbolChange,
)

from services.graph import RepositoryGraph

from .analyzer import IndexedRepository
from .snapshot import Snapshot

_DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_SYMBOL_PATTERNS = {
    ComponentType.FUNCTION: re.compile(r"^\s*(?:async\s+def|def|(?:export\s+)?(?:async\s+)?function)\s+(\w+)"),
    ComponentType.CLASS: re.compile(r"^\s*(?:class|(?:export\s+)?class)\s+(\w+)"),
    ComponentType.API: re.compile(r"^\s*@?(?:router|app)\.(?:get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)"),
}
_STATE_VALUE = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*=\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]")
_SQL_REFERENCE = re.compile(r"\b(?:CREATE\s+TABLE|ALTER\s+TABLE|FROM|JOIN|UPDATE|INTO)\s+([\w.]+)", re.I)
_DB_FIELD = re.compile(r"^\s*([a-zA-Z_]\w*)\s*(?::|=\s*(?:Column|mapped_column)\b)")
_MAX_PATCH_BYTES = 2_000_000
_MAX_DIFF_LINE_BYTES = 100_000
_MAX_FILES = 1_000


class DiffParseError(ValueError):
    pass


class DiffAnalyzer:
    """Parse and materialize patches without executing repository code."""

    def parse(self, patch: str, before_snapshot: Snapshot, after_snapshot_id: str | None = None) -> ChangeSet:
        if not patch.strip():
            raise DiffParseError("Proposed diff is empty")
        if len(patch.encode("utf-8", errors="replace")) > _MAX_PATCH_BYTES:
            raise DiffParseError("Proposed diff exceeds the size limit")
        if any(len(line.encode("utf-8", errors="replace")) > _MAX_DIFF_LINE_BYTES for line in patch.splitlines()):
            raise DiffParseError("Proposed diff contains an oversized line")
        if "\x00" in patch or "GIT binary patch" in patch or "Binary files " in patch:
            raise DiffParseError("Binary patches are not supported")
        files: list[DiffChange] = []
        current: dict | None = None
        old_line = new_line = 0
        seen_paths: set[tuple[str, str]] = set()
        for raw in patch.splitlines():
            header = _DIFF_HEADER.match(raw)
            if header:
                if current:
                    files.append(self._finish(current))
                old_path, new_path = header.groups()
                self._validate_path(old_path)
                self._validate_path(new_path)
                pair = (old_path, new_path)
                if pair in seen_paths:
                    raise DiffParseError("Duplicate diff file entry")
                seen_paths.add(pair)
                if len(seen_paths) > _MAX_FILES:
                    raise DiffParseError("Proposed diff contains too many files")
                current = {"old_path": old_path, "new_path": new_path, "added": [], "deleted": []}
                continue
            if current is None:
                continue
            if raw.startswith("new file mode"):
                current["kind"] = ChangeKind.ADDED
            elif raw.startswith("deleted file mode"):
                current["kind"] = ChangeKind.DELETED
            elif raw.startswith("rename from "):
                current["kind"] = ChangeKind.RENAMED
                current["old_path"] = raw[12:]
                self._validate_path(current["old_path"])
            elif raw.startswith("rename to "):
                current["new_path"] = raw[10:]
                self._validate_path(current["new_path"])
            else:
                hunk = _HUNK_HEADER.match(raw)
                if hunk:
                    old_line, new_line = int(hunk.group(1)), int(hunk.group(3))
                elif raw.startswith("+") and not raw.startswith("+++"):
                    current["added"].append(LineChange(new_line=new_line, content=raw[1:]))
                    new_line += 1
                elif raw.startswith("-") and not raw.startswith("---"):
                    current["deleted"].append(LineChange(old_line=old_line, content=raw[1:]))
                    old_line += 1
                elif not raw.startswith("\\") and (raw.startswith(" ") or raw == ""):
                    old_line += 1
                    new_line += 1
        if current:
            files.append(self._finish(current))
        if not files:
            raise DiffParseError("No git diff file headers were found")
        digest = hashlib.sha256(patch.encode()).hexdigest()
        return ChangeSet(
            before_snapshot_id=before_snapshot.id,
            after_snapshot_id=after_snapshot_id or f"snap-proposed-{digest[:12]}",
            before_commit_sha=before_snapshot.commit_sha,
            after_commit_sha=f"proposed-{digest[:16]}",
            source="PROPOSED_DIFF",
            files=files,
        )

    def compare_refs(self, repository: Path, base_ref: str, target_ref: str) -> tuple[str, str, str]:
        for ref in (base_ref, target_ref):
            if not ref or ref.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._/@{}~^+-]{1,200}", ref):
                raise DiffParseError(f"Unsafe Git ref: {ref}")
        base_sha = self._git(repository, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
        target_sha = self._git(repository, "rev-parse", "--verify", f"{target_ref}^{{commit}}")
        patch = self._git(repository, "diff", "--no-ext-diff", "--no-textconv", "--", base_sha, target_sha)
        return patch, base_sha, target_sha

    def materialize_after(self, repository: Path, patch: str) -> TemporaryDirectory:
        # Browsers commonly omit the terminal newline when filling a textarea; git apply
        # considers an otherwise valid final hunk corrupt without it.
        if not patch.endswith("\n"):
            patch += "\n"
        temporary = TemporaryDirectory(prefix="changetrace-after-")
        target = Path(temporary.name)
        shutil.copytree(
            repository, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "node_modules", ".venv")
        )
        process = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "--ignore-space-change", "-"],
            cwd=target,
            input=patch,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if process.returncode:
            temporary.cleanup()
            raise DiffParseError(f"Patch could not be applied: {process.stderr.strip()[:500]}")
        return temporary

    def enrich(self, change_set: ChangeSet, before: IndexedRepository, after: IndexedRepository) -> ChangeSet:
        before_by_key = {item.stable_key: item for item in before.components}
        after_by_key = {item.stable_key: item for item in after.components}
        enriched = []
        for change in change_set.files:
            old_path, new_path = change.old_path, change.new_path
            before_items = {k: v for k, v in before_by_key.items() if old_path and v.location.file == old_path}
            after_items = {k: v for k, v in after_by_key.items() if new_path and v.location.file == new_path}
            symbols: list[SymbolChange] = []
            for key in sorted(before_items.keys() | after_items.keys()):
                old, new = before_items.get(key), after_items.get(key)
                if old is None and new:
                    kind = ChangeKind.ADDED
                elif new is None and old:
                    kind = ChangeKind.DELETED
                elif old and new and self._component_text(old, before) != self._component_text(new, after):
                    kind = ChangeKind.MODIFIED
                else:
                    continue
                component = new or old
                assert component is not None
                symbols.append(
                    SymbolChange(
                        name=component.name,
                        component_type=component.type,
                        change_kind=kind,
                        before_location=old.location if old else None,
                        after_location=new.location if new else None,
                    )
                )
            enriched.append(change.model_copy(update={"symbol_changes": symbols}))
        return change_set.model_copy(update={"files": enriched})

    def graph_delta(self, before: IndexedRepository, after: IndexedRepository) -> GraphDelta:
        before_graph, after_graph = RepositoryGraph(before), RepositoryGraph(after)
        before_keys = {item.stable_key: item for item in before.components}
        after_keys = {item.stable_key: item for item in after.components}
        added = sorted(after_keys.keys() - before_keys.keys())
        removed = sorted(before_keys.keys() - after_keys.keys())
        modified = sorted(
            key
            for key in before_keys.keys() & after_keys.keys()
            if self._component_text(before_keys[key], before) != self._component_text(after_keys[key], after)
        )
        before_edges = self._stable_edges(before_graph)
        after_edges = self._stable_edges(after_graph)
        return GraphDelta(
            added_components=added,
            removed_components=removed,
            modified_components=modified,
            added_relationships=[after_edges[key] for key in sorted(after_edges.keys() - before_edges.keys())],
            removed_relationships=[before_edges[key] for key in sorted(before_edges.keys() - after_edges.keys())],
        )

    def _finish(self, raw: dict) -> DiffChange:
        added: list[LineChange] = raw["added"]
        deleted: list[LineChange] = raw["deleted"]
        kind = raw.get("kind", ChangeKind.MODIFIED)
        symbols = self._line_symbols(added, ChangeKind.ADDED) + self._line_symbols(deleted, ChangeKind.DELETED)
        states = [
            StateValueChange(state_machine="unknown", value=match.group(2), change_kind=ChangeKind.ADDED)
            for line in added
            if (match := _STATE_VALUE.match(line.content))
        ]
        states += [
            StateValueChange(state_machine="unknown", value=match.group(2), change_kind=ChangeKind.DELETED)
            for line in deleted
            if (match := _STATE_VALUE.match(line.content))
        ]
        routes = [
            match.group(1)
            for line in added + deleted
            if (match := _SYMBOL_PATTERNS[ComponentType.API].match(line.content))
        ]
        db_fields = [match.group(1) for line in added + deleted if (match := _DB_FIELD.match(line.content))]
        sql = [match.group(1) for line in added + deleted for match in _SQL_REFERENCE.finditer(line.content)]
        return DiffChange(
            old_path=raw["old_path"],
            new_path=raw["new_path"],
            change_kind=kind,
            added_lines=added,
            deleted_lines=deleted,
            symbol_changes=symbols,
            state_changes=states,
            changed_api_routes=routes,
            changed_db_fields=db_fields,
            changed_sql_references=sql,
        )

    @staticmethod
    def _line_symbols(lines: list[LineChange], kind: ChangeKind) -> list[SymbolChange]:
        result = []
        for line in lines:
            for component_type, pattern in _SYMBOL_PATTERNS.items():
                if match := pattern.match(line.content):
                    number = line.new_line if kind == ChangeKind.ADDED else line.old_line
                    location = SourceLocation(
                        file="unknown", line_start=number or 1, line_end=number or 1, symbol=match.group(1)
                    )
                    result.append(
                        SymbolChange(
                            name=match.group(1),
                            component_type=component_type,
                            change_kind=kind,
                            after_location=location if kind == ChangeKind.ADDED else None,
                            before_location=location if kind == ChangeKind.DELETED else None,
                        )
                    )
        return result

    @staticmethod
    def _validate_path(value: str) -> None:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or value.startswith(("/", "\\"))
            or "\\" in value
            or re.match(r"^[A-Za-z]:", value)
        ):
            raise DiffParseError(f"Unsafe patch path: {value}")

    @staticmethod
    def _git(repository: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()

    @staticmethod
    def _component_text(component, index: IndexedRepository) -> str:
        lines = index.file_text.get(component.location.file, "").splitlines()
        return "\n".join(lines[component.location.line_start - 1 : component.location.line_end])

    @staticmethod
    def _stable_edges(graph: RepositoryGraph):
        result = {}
        for source, target, data in graph.graph.edges(data=True):
            source_key = graph.components[source].stable_key
            target_key = graph.components[target].stable_key
            key = (source_key, target_key, data["relationship"])
            from changetrace_schemas import GraphEdge

            result[key] = GraphEdge(source=source_key, target=target_key, relationship=data["relationship"])
        return result
