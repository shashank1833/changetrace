from pathlib import Path

from changetrace_schemas import ImpactStatus

from services.changes import ChangeInterpreter
from services.graph import RepositoryGraph
from services.impact import ImpactEngine
from services.repository_analysis import RepositoryAnalyzer, SnapshotService


def likely(root: Path) -> set[tuple[str, str]]:
    index = RepositoryAnalyzer().scan(root, "snapshot", "commit")
    intent = ChangeInterpreter().interpret("Require subscription authorization before account cancellation")
    components, _, _ = ImpactEngine().discover(index, RepositoryGraph(index), intent)
    return {
        (item.location.file, item.name)
        for item in components
        if item.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
    }


def test_unrelated_comment_and_file_do_not_change_likely_impact(tmp_path: Path):
    source = tmp_path / "subscription.py"
    source.write_text("def authorize_cancellation(subscription, user):\n    return subscription.owner == user\n")
    baseline = likely(tmp_path)
    source.write_text(
        "# harmless formatting note\n\n"
        "def authorize_cancellation(subscription, user):\n"
        "    return subscription.owner == user\n"
    )
    (tmp_path / "unrelated.py").write_text("value = 'nothing relevant'\n")
    assert likely(tmp_path) == baseline


def test_snapshot_hash_changes_for_any_source_mutation(tmp_path: Path):
    source = tmp_path / "a.py"
    for first, second in [("x=1\n", "x=2\n"), ("a\n", "a\n# comment\n"), ("", "x\n")]:
        source.write_text(first)
        before = SnapshotService().from_local(tmp_path).commit_sha
        source.write_text(second)
        after = SnapshotService().from_local(tmp_path).commit_sha
        assert before != after
