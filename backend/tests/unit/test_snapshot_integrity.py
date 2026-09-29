from pathlib import Path

from services.evidence import EvidenceEngine
from services.repository_analysis import RepositoryAnalyzer, SnapshotService


def test_snapshot_identity_is_stable_and_changes_with_content(tmp_path: Path):
    source = tmp_path / "service.py"
    source.write_text("value = 1\n")
    first = SnapshotService().from_local(tmp_path)
    second = SnapshotService().from_local(tmp_path)
    assert first.id == second.id
    assert first.commit_sha == second.commit_sha

    source.write_text("value = 2\n")
    changed = SnapshotService().from_local(tmp_path)
    assert changed.id != first.id


def test_altered_source_rejects_stale_evidence(tmp_path: Path):
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n")
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    evidence = next(item for item in index.evidence if item.location.symbol == "run")
    source.write_text("def run():\n    return 2\n")
    altered = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    assert not EvidenceEngine().validate(evidence, altered)


def test_symlink_outside_snapshot_is_not_hashed_or_analyzed(tmp_path: Path):
    outside = tmp_path.parent / "outside-secret.py"
    outside.write_text("SECRET = 'do-not-index'\n")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(outside)
    except OSError:
        return  # Windows developer environments may not grant symlink privileges.
    first = SnapshotService().from_local(tmp_path)
    outside.write_text("SECRET = 'changed'\n")
    second = SnapshotService().from_local(tmp_path)
    index = RepositoryAnalyzer().scan(tmp_path, first.id, first.commit_sha)
    assert first.id == second.id
    assert "linked.py" not in index.file_text


def test_missing_source_rejects_evidence(tmp_path: Path):
    (tmp_path / "service.py").write_text("def run():\n    return 1\n")
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    evidence = next(item for item in index.evidence if item.location.symbol == "run")
    (tmp_path / "service.py").unlink()
    missing = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    assert not EvidenceEngine().validate(evidence, missing)
