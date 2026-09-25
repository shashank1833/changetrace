#!/usr/bin/env python3
"""ChangeTrace Security Scanner.

Performs static analysis, secret scanning, dependency vulnerability checking,
and Dockerfile best-practice auditing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from services.retention.service import CREDENTIAL_PATTERNS

REPO_ROOT = Path(__file__).resolve().parents[2]
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", ".audit-venv", "node_modules", "dist",
    "build", "__pycache__", ".gemini", "tests", "site-packages",
}
ALLOWED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".sql", ".sh", ".env.example", ".md",
}


def scan_secrets(root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    """Scan all repository files for potential hardcoded secrets or sensitive credentials."""
    findings = []
    special_names = {"Dockerfile", "api.Dockerfile", "web.Dockerfile", "Makefile"}
    for path in root.rglob("*"):
        if path.is_file():
            if any(part in EXCLUDE_DIRS or "venv" in part.lower() for part in path.parts):
                continue
            if path.suffix.lower() not in ALLOWED_EXTENSIONS and path.name not in special_names:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                # Skip comments indicating examples or mock tokens
                if "mock" in line.lower() or "example" in line.lower() or "placeholder" in line.lower():
                    continue
                for pattern in CREDENTIAL_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        findings.append({
                            "type": "SECRET_EXPOSURE",
                            "file": path.relative_to(REPO_ROOT).as_posix(),
                            "line": idx,
                            "match": match.group(0)[:15] + "...",
                            "rule": pattern.pattern[:40],
                        })
    return findings


def audit_dockerfiles(root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    """Check Dockerfile configurations for security best practices."""
    findings: list[dict[str, Any]] = []
    dockerfiles = list(root.glob("**/Dockerfile*")) + list(root.glob("**/*.Dockerfile"))
    for df in dockerfiles:
        if any(part in EXCLUDE_DIRS for part in df.parts):
            continue
        try:
            content = df.read_text(encoding="utf-8")
        except Exception:
            continue

        rel_path = df.relative_to(REPO_ROOT).as_posix()
        lines = content.splitlines()

        has_user = any(re.match(r"^\s*USER\s+", line, re.IGNORECASE) for line in lines)
        is_web_server = "nginx" in df.name.lower() or "web" in df.name.lower() or "nginx" in content.lower()
        if not has_user and not is_web_server:
            findings.append({
                "type": "CONTAINER_ROOT_EXECUTION",
                "file": rel_path,
                "message": "Dockerfile does not declare a non-root USER instruction.",
            })

        for idx, line in enumerate(lines, start=1):
            if re.search(r"FROM\s+[^:]+:latest", line, re.IGNORECASE):
                findings.append({
                    "type": "UNPINNED_CONTAINER_BASE",
                    "file": rel_path,
                    "line": idx,
                    "message": "Base image uses mutable ':latest' tag instead of pinned digest or version.",
                })
            if re.search(r"ENV\s+.*(SECRET|PASSWORD|TOKEN|KEY)\s*=", line, re.IGNORECASE):
                findings.append({
                    "type": "CONTAINER_HARDCODED_ENV_SECRET",
                    "file": rel_path,
                    "line": idx,
                    "message": "Potential credential baked into image ENV instruction.",
                })
    return findings


def audit_dependencies() -> list[dict[str, Any]]:
    """Run pip-audit and npm audit if available."""
    findings = []
    # Check pip-audit
    try:
        cmd = ["pip-audit", "--format", "json"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=False)
        if res.returncode != 0 and res.stdout:
            findings.append({"type": "PYTHON_DEPENDENCY_VULNERABILITY", "output": res.stdout[:500]})
    except FileNotFoundError:
        pass

    # Check npm audit
    npm_dir = REPO_ROOT / "apps" / "web"
    if (npm_dir / "package.json").exists():
        try:
            res = subprocess.run(["npm", "audit", "--json"], capture_output=True, text=True, cwd=npm_dir, check=False)
            if res.returncode != 0 and res.stdout:
                findings.append({"type": "NPM_DEPENDENCY_VULNERABILITY", "output": res.stdout[:500]})
        except FileNotFoundError:
            pass

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="ChangeTrace Static Security and SAST Scanner")
    parser.add_argument("--secrets-only", action="store_true", help="Only run secret scanning")
    parser.add_argument("--docker-only", action="store_true", help="Only run Dockerfile audits")
    args = parser.parse_args()

    all_findings = []

    if not args.docker_only:
        print("[*] Scanning repository for exposed credentials...")
        secret_findings = scan_secrets()
        all_findings.extend(secret_findings)
        print(f"    Found {len(secret_findings)} secret exposures.")

    if not args.secrets_only:
        print("[*] Auditing Dockerfiles for container security...")
        docker_findings = audit_dockerfiles()
        all_findings.extend(docker_findings)
        print(f"    Found {len(docker_findings)} container configuration alerts.")

    print(f"\nTotal Security Findings: {len(all_findings)}")
    for f in all_findings:
        loc = f"{f.get('file', '')}:{f.get('line', '')}" if f.get('file') else ""
        print(f"  [{f['type']}] {loc} - {f.get('message', f.get('rule', ''))}")

    # Return 0 if no high severity secret exposures, else 1
    if any(f["type"] == "SECRET_EXPOSURE" for f in all_findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
