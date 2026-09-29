from pathlib import Path
import pytest
from services.repository_analysis.diff import DiffAnalyzer, DiffParseError


def test_reject_git_flag_injection_in_refs(tmp_path: Path):
    analyzer = DiffAnalyzer()
    
    # Flags starting with - or -- must be rejected
    with pytest.raises(DiffParseError) as exc_info:
        analyzer.compare_refs(tmp_path, "--output=/tmp/pwn", "main")
    assert "Unsafe Git ref" in str(exc_info.value)

    with pytest.raises(DiffParseError) as exc_info:
        analyzer.compare_refs(tmp_path, "main", "-v")
    assert "Unsafe Git ref" in str(exc_info.value)

    with pytest.raises(DiffParseError) as exc_info:
        analyzer.compare_refs(tmp_path, "", "main")
    assert "Unsafe Git ref" in str(exc_info.value)
