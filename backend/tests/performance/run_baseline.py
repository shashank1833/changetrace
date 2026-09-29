from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from services.changes import ChangeInterpreter
from services.evidence import EvidenceEngine
from services.graph import RepositoryGraph
from services.impact import ImpactEngine
from services.repository_analysis import RepositoryAnalyzer, SnapshotService

SIZES = (1_000, 10_000, 50_000, 100_000)
REQUEST = "Require authorization before updating a subscription status."


def generate(root: Path, lines: int) -> None:
    source = root / "subscription_service.py"
    body = [
        "def update_subscription(subscription, user):",
        "    if subscription.owner_id != user.id:",
        "        raise PermissionError('owner required')",
        "    subscription.status = 'ACTIVE'",
        "    return subscription",
    ]
    body.extend(f"VALUE_{number} = {number}" for number in range(max(0, lines - len(body))))
    source.write_text("\n".join(body) + "\n")


def measure(lines: int) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory(prefix="changetrace-perf-") as directory:
        root = Path(directory)
        generate(root, lines)
        tracemalloc.start()
        total_start = time.perf_counter()
        started = time.perf_counter()
        snapshot = SnapshotService().from_local(root)
        ingestion = time.perf_counter() - started
        started = time.perf_counter()
        index = RepositoryAnalyzer().scan(root, snapshot.id, snapshot.commit_sha)
        parsing = time.perf_counter() - started
        started = time.perf_counter()
        graph = RepositoryGraph(index)
        graph_time = time.perf_counter() - started
        started = time.perf_counter()
        intent = ChangeInterpreter().interpret(REQUEST)
        components, _, _ = ImpactEngine().discover(index, graph, intent)
        impact = time.perf_counter() - started
        started = time.perf_counter()
        EvidenceEngine().collect(index, components)
        evidence = time.perf_counter() - started
        total = time.perf_counter() - total_start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "lines": lines,
            "ingestion_seconds": round(ingestion, 4),
            "parsing_seconds": round(parsing, 4),
            "graph_seconds": round(graph_time, 4),
            "impact_seconds": round(impact, 4),
            "evidence_seconds": round(evidence, 4),
            "total_seconds": round(total, 4),
            "peak_memory_mib": round(peak / 1024 / 1024, 2),
            "llm_calls": 0,
            "queue_wait_seconds": 0,
        }


if __name__ == "__main__":
    output = {"environment": "synthetic single-file Python repositories", "results": [measure(size) for size in SIZES]}
    path = Path(__file__).with_name("results.json")
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
