from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp


@dataclass(frozen=True)
class Snapshot:
    id: str
    repository: str
    commit_sha: str
    path: Path


class SnapshotService:
    def from_local(self, path: Path) -> Snapshot:
        resolved = path.resolve()
        if not resolved.is_dir():
            raise ValueError("Repository path must be a directory")
        content_digest = self._directory_hash(resolved)
        commit = self._git_sha(resolved) or content_digest
        snapshot_id = f"snap-{content_digest[:12]}"
        return Snapshot(snapshot_id, resolved.name, commit, resolved)

    def clone_github(
        self, clone_url: str, access_token: str | None = None, workspace_root: Path | None = None
    ) -> Snapshot:
        if not clone_url.startswith("https://github.com/"):
            raise ValueError("Only HTTPS GitHub URLs are accepted")
        directory = str(workspace_root.resolve()) if workspace_root else None
        target = Path(mkdtemp(prefix="changetrace-snapshot-", dir=directory))
        url = clone_url
        if access_token:
            url = clone_url.replace("https://", f"https://x-access-token:{access_token}@", 1)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(target)],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return self.from_local(target)

    def materialize_git_ref(self, repository: Path, commit_sha: str) -> tuple[Snapshot, TemporaryDirectory[str]]:
        if not commit_sha or not all(character in "0123456789abcdefABCDEF" for character in commit_sha):
            raise ValueError("Git comparison must resolve to a commit SHA")
        temporary = TemporaryDirectory(prefix="changetrace-ref-")
        target = Path(temporary.name)
        try:
            archive = subprocess.run(
                ["git", "-C", str(repository), "archive", "--format=tar", commit_sha],
                check=True,
                capture_output=True,
                timeout=60,
            ).stdout
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
                bundle.extractall(target, filter="data")
        except Exception:
            temporary.cleanup()
            raise
        snapshot = Snapshot(
            id=f"snap-{commit_sha[:12]}",
            repository=repository.resolve().name,
            commit_sha=commit_sha,
            path=target,
        )
        return snapshot, temporary

    @staticmethod
    def _git_sha(path: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return None

    @staticmethod
    def _directory_hash(path: Path) -> str:
        digest = hashlib.sha256()
        ignored = {".git", "node_modules", ".venv", "venv", "dist", "build", "coverage", "__pycache__"}
        for file in sorted(path.rglob("*")):
            relative = file.relative_to(path)
            if file.is_symlink() or not file.is_file() or any(part in ignored for part in relative.parts):
                continue
            digest.update(relative.as_posix().encode())
            try:
                digest.update(file.read_bytes())
            except OSError:
                continue
        return digest.hexdigest()
