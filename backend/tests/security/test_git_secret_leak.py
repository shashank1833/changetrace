import subprocess
from pathlib import Path
import pytest
from services.repository_analysis.snapshot import SnapshotService


def test_clone_github_redacts_tokens_on_error(monkeypatch):
    # Simulate a git clone failure with an access token
    def mock_subprocess_run(cmd, *args, **kwargs):
        raise subprocess.CalledProcessError(128, cmd, output="", stderr="fatal: authentication failed")

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    service = SnapshotService()
    secret_token = "ghs_SUPER_SECRET_GITHUB_TOKEN_12345"

    with pytest.raises(Exception) as exc_info:
        service.clone_github("https://github.com/org/repo", access_token=secret_token)

    # Ensure the secret token is NOT leaked in the raised exception string
    assert secret_token not in str(exc_info.value)
