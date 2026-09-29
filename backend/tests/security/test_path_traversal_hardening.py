import pytest
from pathlib import Path
from apps.api.changetrace_api.main import _safe_local_path


def test_arbitrary_host_path_is_rejected(tmp_path: Path):
    # A directory completely outside workspace or repo root must be rejected
    external_dir = tmp_path / "outside_workspace"
    external_dir.mkdir()
    
    with pytest.raises(ValueError, match="Repository path is outside configured repository roots"):
        _safe_local_path(str(external_dir))


def test_parent_directory_traversal_is_rejected():
    with pytest.raises(ValueError, match="Repository path is outside configured repository roots"):
        _safe_local_path("../../Windows")
