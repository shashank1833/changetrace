from pathlib import Path
import pytest
from workers.analysis.pipeline import AnalysisPipeline
from services.repository_analysis import DiffAnalyzer


def test_pipeline_cleans_up_temporary_directories_on_failure(tmp_path: Path, monkeypatch):
    (tmp_path / "main.py").write_text("def hello(): pass\n")
    
    created_dirs = []
    orig_materialize = DiffAnalyzer.materialize_after

    def tracked_materialize(self, repository, patch):
        td = orig_materialize(self, repository, patch)
        created_dirs.append(Path(td.name))
        return td

    monkeypatch.setattr(DiffAnalyzer, "materialize_after", tracked_materialize)

    from services.verification import ResultVerifier
    def mock_verify(*args, **kwargs):
        raise RuntimeError("Simulated pipeline failure")
    
    monkeypatch.setattr(ResultVerifier, "verify", mock_verify)

    pipeline = AnalysisPipeline()
    diff = "diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n@@ -1,1 +1,2 @@\n def hello(): pass\n+# new line\n"

    with pytest.raises(RuntimeError, match="Simulated pipeline failure"):
        pipeline.run(tmp_path, "Add a new feature to main", proposed_diff=diff)

    assert len(created_dirs) == 1
    assert not created_dirs[0].exists(), f"Staging directory leaked: {created_dirs[0]}"
