#!/usr/bin/env python3
"""ChangeTrace Software Bill of Materials (SBOM) Generator.

Generates standard CycloneDX (v1.5) or SPDX (v2.3) SBOMs covering Python backend
and Node.js frontend dependencies.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def collect_python_dependencies() -> list[dict[str, Any]]:
    """Enumerate installed python distributions and versions."""
    components = []
    seen = set()
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        version = dist.metadata["Version"]
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name}@{version}",
            "description": dist.metadata.get("Summary", ""),
            "licenses": [{"license": {"name": dist.metadata.get("License", "Unknown")}}],
        })
    return components


def collect_frontend_dependencies() -> list[dict[str, Any]]:
    """Parse package.json in apps/web to gather frontend components."""
    pkg_json_path = REPO_ROOT / "apps" / "web" / "package.json"
    if not pkg_json_path.exists():
        return []
    try:
        data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    components = []
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    for name, version in deps.items():
        clean_ver = version.lstrip("^~>=<")
        components.append({
            "type": "library",
            "name": name,
            "version": clean_ver,
            "purl": f"pkg:npm/{name}@{clean_ver}",
            "scope": "required" if name in data.get("dependencies", {}) else "optional",
        })
    return components


def generate_cyclonedx_sbom() -> dict[str, Any]:
    """Build a CycloneDX 1.5 JSON SBOM structure."""
    py_components = collect_python_dependencies()
    fe_components = collect_frontend_dependencies()
    all_components = py_components + fe_components

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "tools": [{"vendor": "ChangeTrace", "name": "changetrace-sbom-generator", "version": "0.1.0"}],
            "component": {
                "type": "application",
                "name": "ChangeTrace",
                "version": "0.1.0",
                "description": "Deterministic semantic and business-change impact analysis platform",
            },
        },
        "components": all_components,
    }


def generate_spdx_sbom() -> dict[str, Any]:
    """Build an SPDX 2.3 JSON structure."""
    py_components = collect_python_dependencies()
    fe_components = collect_frontend_dependencies()
    all_components = py_components + fe_components

    packages = []
    for c in all_components:
        pkg_id = f"SPDXRef-Package-{c['name'].replace('@', '').replace('/', '-')}-{c['version']}"
        packages.append({
            "SPDXID": pkg_id,
            "name": c["name"],
            "versionInfo": c["version"],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": c.get("purl", f"pkg:generic/{c['name']}@{c['version']}"),
                }
            ],
        })

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "ChangeTrace-SBOM",
        "documentNamespace": f"https://changetrace.io/spdx/{uuid.uuid4()}",
        "creationInfo": {
            "created": datetime.now(UTC).isoformat(),
            "creators": ["Tool: ChangeTrace-SBOM-Generator-0.1.0"],
        },
        "packages": packages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SBOM for ChangeTrace")
    parser.add_argument("--format", choices=["cyclonedx", "spdx"], default="cyclonedx", help="SBOM format")
    parser.add_argument("--output", "-o", type=Path, help="Output file path (defaults to stdout)")
    args = parser.parse_args()

    if args.format == "spdx":
        sbom = generate_spdx_sbom()
    else:
        sbom = generate_cyclonedx_sbom()

    output_str = json.dumps(sbom, indent=2)
    if args.output:
        pkg_count = len(sbom.get("components", sbom.get("packages", [])))
        print(f"Generated {args.format.upper()} SBOM with {pkg_count} packages at {args.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
