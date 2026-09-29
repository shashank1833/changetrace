from pathlib import Path

from services.graph import RepositoryGraph
from services.repository_analysis import RepositoryAnalyzer


def test_same_named_functions_in_other_modules_are_not_call_targets(tmp_path: Path):
    (tmp_path / "a.py").write_text("def load_order():\n    return 1\n\ndef use():\n    return load_order()\n")
    (tmp_path / "b.py").write_text("def load_order():\n    return 2\n")
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    graph = RepositoryGraph(index)
    calls = {
        (graph.components[source].location.file, graph.components[target].location.file)
        for source, target, data in graph.graph.edges(data=True)
        if data["relationship"] == "CALLS"
    }
    assert ("a.py", "a.py") in calls
    assert ("a.py", "b.py") not in calls


def test_imports_calls_and_contains_remain_distinct(tmp_path: Path):
    (tmp_path / "target.py").write_text("def run():\n    return 1\n")
    (tmp_path / "caller.py").write_text("from target import run\n\ndef invoke():\n    return run()\n")
    graph = RepositoryGraph(RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit"))
    relationships = {data["relationship"] for _, _, data in graph.graph.edges(data=True)}
    assert {"IMPORTS", "CALLS", "CONTAINS"} <= relationships
