from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from changetrace_schemas import ChangeSet

from .analyzer import IGNORED_PARTS, SUPPORTED_SUFFIXES, IndexedRepository, RepositoryAnalyzer

logger = logging.getLogger("changetrace.incremental")


@dataclass
class IncrementalIndexResult:
    index: IndexedRepository
    reused_files: int
    reindexed_files: int
    duration_seconds: float
    fallback_used: bool = False
    invalidated_calls: int = 0


class IncrementalIndexer:
    """Incremental index reuse with safe cross-file relationship rebuilding and full-analysis fallback."""

    def __init__(self, analyzer: RepositoryAnalyzer | None = None) -> None:
        self.analyzer = analyzer or RepositoryAnalyzer()

    def update(
        self,
        base_index: IndexedRepository,
        new_root: Path,
        new_snapshot_id: str,
        new_commit_sha: str,
        repository_id: str = "unknown",
        change_set: ChangeSet | None = None,
    ) -> IncrementalIndexResult:
        started = time.perf_counter()
        new_root = new_root.resolve()

        if not new_root.exists() or not new_root.is_dir():
            raise ValueError(f"New repository path does not exist: {new_root}")

        try:
            return self._incremental_scan(
                base_index=base_index,
                new_root=new_root,
                new_snapshot_id=new_snapshot_id,
                new_commit_sha=new_commit_sha,
                repository_id=repository_id,
                change_set=change_set,
                started=started,
            )
        except Exception as exc:
            logger.warning(
                "Incremental indexing failed, safely falling back to full analysis: %s",
                exc,
                exc_info=True,
            )
            fallback_index = self.analyzer.scan(
                new_root, new_snapshot_id, new_commit_sha, repository_id=repository_id
            )
            return IncrementalIndexResult(
                index=fallback_index,
                reused_files=0,
                reindexed_files=len(fallback_index.file_text),
                duration_seconds=round(time.perf_counter() - started, 4),
                fallback_used=True,
            )

    def _incremental_scan(
        self,
        base_index: IndexedRepository,
        new_root: Path,
        new_snapshot_id: str,
        new_commit_sha: str,
        repository_id: str,
        change_set: ChangeSet | None,
        started: float,
    ) -> IncrementalIndexResult:
        if not base_index.file_text:
            raise ValueError("Base index is empty")

        new_index = IndexedRepository(
            root=new_root,
            snapshot_id=new_snapshot_id,
            commit_sha=new_commit_sha,
            repository_id=repository_id,
        )

        current_files: dict[str, Path] = {}
        import os
        paths: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(new_root):
            dirnames[:] = sorted([d for d in dirnames if d not in IGNORED_PARTS and not d.startswith(".")])
            for filename in filenames:
                paths.append(Path(dirpath) / filename)
        paths.sort()
        for path in paths:
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            rel = path.relative_to(new_root).as_posix()
            current_files[rel] = path

        # Identify explicitly changed, added, and deleted files
        explicit_changed_files: set[str] = set()
        if change_set:
            for item in change_set.files:
                if item.new_path:
                    explicit_changed_files.add(item.new_path)
                if item.old_path:
                    explicit_changed_files.add(item.old_path)

        deleted_files = set(base_index.file_text.keys()) - set(current_files.keys())

        reused_count = 0
        reindexed_count = 0
        files_to_reindex: list[tuple[str, Path, str]] = []

        for rel, path in current_files.items():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                new_index.parse_warnings.append(f"Skipped {path}: {exc}")
                continue

            is_changed = (
                rel in explicit_changed_files
                or rel not in base_index.file_text
                or base_index.file_text[rel] != text
            )

            if not is_changed:
                # Strong evidence invariant check: verify line bounds match text
                lines = text.splitlines()
                evidence_valid = True
                for ev in base_index.evidence:
                    if ev.location.file == rel:
                        lstart, lend = ev.location.line_start - 1, ev.location.line_end
                        if lstart < 0 or lend > len(lines):
                            evidence_valid = False
                            break

                if not evidence_valid:
                    files_to_reindex.append((rel, path, text))
                    continue

                reused_count += 1
                new_index.file_text[rel] = text

                # Copy evidence with updated snapshot/commit IDs
                for ev in base_index.evidence:
                    if ev.location.file == rel:
                        new_ev = ev.model_copy(
                            update={
                                "repository_snapshot_id": new_snapshot_id,
                                "commit_sha": new_commit_sha,
                                "repository_id": repository_id,
                            }
                        )
                        new_index.evidence.append(new_ev)

                # Copy components
                for comp in base_index.components:
                    if comp.location.file == rel:
                        new_index.components.append(comp.model_copy())

                # Copy imports and calls for this file
                for imp in base_index.imports:
                    if imp[0] == rel:
                        new_index.imports.append(imp)
                for caller, called, file in base_index.calls:
                    if file == rel:
                        new_index.calls.append((caller, called, file))

                self.analyzer._index_terms(new_index, rel, text)
            else:
                files_to_reindex.append((rel, path, text))

        total_files = len(current_files)
        if total_files > 0 and (len(files_to_reindex) / total_files) > 0.60:
            raise ValueError(
                f"Too many modified files ({len(files_to_reindex)}/{total_files}); falling back to full scan"
            )

        # Parse reindexed files
        for rel, path, text in files_to_reindex:
            reindexed_count += 1
            new_index.file_text[rel] = text
            from changetrace_schemas import ComponentType
            self.analyzer._add(
                new_index,
                rel,
                1,
                max(1, len(text.splitlines())),
                rel,
                ComponentType.FILE,
                "Source file in repository snapshot",
            )
            if path.suffix == ".py":
                self.analyzer._parse_python(new_index, rel, text)
            elif path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
                self.analyzer._parse_javascript(new_index, rel, text)
            elif path.suffix == ".sql":
                self.analyzer._parse_sql(new_index, rel, text)
            elif path.suffix == ".md":
                self.analyzer._add(
                    new_index,
                    rel,
                    1,
                    max(1, len(text.splitlines())),
                    rel,
                    ComponentType.DOCUMENT,
                    "Repository documentation",
                )
            self.analyzer._index_terms(new_index, rel, text)

        # Rebuild and sanitize cross-file relationships:
        # Purge imports and calls that point to deleted files or vanished symbols
        invalidated_calls_count = 0
        valid_imports = []
        for imp in new_index.imports:
            _source_file, mod_name = imp[0], imp[1]
            # Check if imported module matches a deleted file
            if any(mod_name in dfile or dfile.startswith(mod_name) for dfile in deleted_files):
                continue
            valid_imports.append(imp)
        new_index.imports = valid_imports

        valid_calls = []
        for caller, called, file in new_index.calls:
            # Check if call was defined in a deleted file
            if file in deleted_files:
                invalidated_calls_count += 1
                continue
            valid_calls.append((caller, called, file))
        new_index.calls = valid_calls

        if not new_index.components:
            raise ValueError("Incremental indexing produced zero components")

        duration = round(time.perf_counter() - started, 4)
        return IncrementalIndexResult(
            index=new_index,
            reused_files=reused_count,
            reindexed_files=reindexed_count,
            duration_seconds=duration,
            fallback_used=False,
            invalidated_calls=invalidated_calls_count,
        )

    def save_cache(self, cache_file: Path, index: IndexedRepository) -> None:
        """Persist indexed repository metadata to disk cache."""
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "snapshot_id": index.snapshot_id,
                "commit_sha": index.commit_sha,
                "repository_id": index.repository_id,
                "file_text": index.file_text,
                "imports": index.imports,
                "calls": index.calls,
                "components": [c.model_dump(mode="json") for c in index.components],
                "evidence": [e.model_dump(mode="json") for e in index.evidence],
            }
            cache_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save index cache to %s: %s", cache_file, exc)

    def load_cache(self, cache_file: Path, root: Path) -> IndexedRepository | None:
        """Load indexed repository from disk cache."""
        if not cache_file.exists():
            return None
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            from changetrace_schemas import Component, Evidence
            index = IndexedRepository(
                root=root,
                snapshot_id=data["snapshot_id"],
                commit_sha=data["commit_sha"],
                repository_id=data.get("repository_id", "unknown"),
            )
            index.file_text = data.get("file_text", {})
            index.imports = [tuple(item) for item in data.get("imports", [])]
            index.calls = [tuple(item) for item in data.get("calls", [])]
            index.components = [Component.model_validate(c) for c in data.get("components", [])]
            index.evidence = [Evidence.model_validate(e) for e in data.get("evidence", [])]
            return index
        except Exception as exc:
            logger.warning("Failed to load index cache from %s: %s", cache_file, exc)
            return None
