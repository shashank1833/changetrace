from pathlib import Path

from services.repository_analysis import IncrementalIndexer, RepositoryAnalyzer

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_incremental_indexer_reuses_unchanged_files(tmp_path: Path):
    # Setup initial repository
    f1 = tmp_path / "mod1.py"
    f2 = tmp_path / "mod2.py"
    f1.write_text("def func1():\n    return 'hello'\n")
    f2.write_text("def func2():\n    return 'world'\n")

    analyzer = RepositoryAnalyzer()
    base_index = analyzer.scan(tmp_path, "snap-1", "commit-1")
    assert len(base_index.components) > 0

    # Modify only mod2.py
    f2.write_text("def func2():\n    return 'updated world'\n")

    indexer = IncrementalIndexer(analyzer)
    result = indexer.update(
        base_index=base_index,
        new_root=tmp_path,
        new_snapshot_id="snap-2",
        new_commit_sha="commit-2",
    )

    assert result.reused_files >= 1
    assert result.reindexed_files >= 1
    assert result.fallback_used is False
    assert result.index.snapshot_id == "snap-2"
    assert any("updated world" in ev.snippet for ev in result.index.evidence)


def test_incremental_indexer_deleted_file_invalidation(tmp_path: Path):
    f1 = tmp_path / "service.py"
    f2 = tmp_path / "legacy.py"
    f1.write_text("from legacy import old_helper\ndef run(): old_helper()\n")
    f2.write_text("def old_helper(): pass\n")

    analyzer = RepositoryAnalyzer()
    base_index = analyzer.scan(tmp_path, "snap-1", "commit-1")

    # Delete legacy.py and update service.py
    f2.unlink()
    f1.write_text("def run(): pass\n")

    indexer = IncrementalIndexer(analyzer)
    result = indexer.update(
        base_index=base_index,
        new_root=tmp_path,
        new_snapshot_id="snap-2",
        new_commit_sha="commit-2",
    )

    # Legacy file was deleted, cross-file relationships pointing to legacy.py must be purged
    assert not any("legacy" in imp[1] for imp in result.index.imports)
    assert not any(c[2] == "legacy.py" for c in result.index.calls)


def test_incremental_indexer_cache_persistence(tmp_path: Path):
    f1 = tmp_path / "app.py"
    f1.write_text("def main(): return 42\n")

    analyzer = RepositoryAnalyzer()
    index = analyzer.scan(tmp_path, "snap-cache", "sha-abc1234")

    indexer = IncrementalIndexer(analyzer)
    cache_file = tmp_path / ".cache" / "index.json"
    indexer.save_cache(cache_file, index)

    assert cache_file.exists()

    loaded = indexer.load_cache(cache_file, root=tmp_path)
    assert loaded is not None
    assert loaded.snapshot_id == "snap-cache"
    assert loaded.commit_sha == "sha-abc1234"
    assert len(loaded.components) == len(index.components)


def test_incremental_indexer_safe_fallback_on_corrupt_base(tmp_path: Path):
    f1 = tmp_path / "mod.py"
    f1.write_text("def hello(): pass\n")

    analyzer = RepositoryAnalyzer()
    from services.repository_analysis.analyzer import IndexedRepository
    corrupt_base = IndexedRepository(root=tmp_path, snapshot_id="corrupt", commit_sha="corrupt")

    indexer = IncrementalIndexer(analyzer)
    result = indexer.update(
        base_index=corrupt_base,
        new_root=tmp_path,
        new_snapshot_id="snap-fallback",
        new_commit_sha="commit-fallback",
    )

    assert result.fallback_used is True
    assert result.index.snapshot_id == "snap-fallback"
    assert len(result.index.components) > 0
