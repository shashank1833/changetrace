from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("changetrace.sandbox")


class SandboxViolationError(RuntimeError):
    """Raised when repository parsing exceeds configured CPU, memory, or size safety limits."""
    pass


@dataclass
class SandboxLimits:
    max_file_size_bytes: int = 5_000_000  # 5 MB
    max_total_bytes: int = 100_000_000  # 100 MB
    max_files_count: int = 5_000
    max_scan_seconds: float = 60.0


class ParserSandbox:
    """Enforces execution and resource boundaries on repository parsing."""

    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits or SandboxLimits()

    def validate_path(self, path: Path, root: Path) -> Path:
        """Verify that path does not escape the repository boundary via symlinks or traversal."""
        resolved = path.resolve()
        resolved_root = root.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError:
            raise SandboxViolationError(f"Symlink or path traversal outside repository root: {path}") from None
        return resolved

    def check_file_size(self, path: Path) -> int:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise SandboxViolationError(f"Cannot stat file {path}: {exc}") from exc
        if size > self.limits.max_file_size_bytes:
            raise SandboxViolationError(
                f"File {path.name} exceeds max size ({size} > {self.limits.max_file_size_bytes} bytes)"
            )
        return size

    def apply_process_limits(self) -> None:
        """Apply OS-level memory limits if running on POSIX systems without killing server process."""
        if sys.platform != "win32":
            try:
                import resource
                # Address space memory limit (1 GB)
                mem_limit = 1024 * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
                logger.info("Configured POSIX resource limits (RLIMIT_AS)")
            except Exception as exc:
                logger.debug("Could not set POSIX resource limits: %s", exc)
