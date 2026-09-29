import os
import re
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from apps.api.changetrace_api.config import Settings
from apps.api.changetrace_api.main import _safe_local_path, _set_security_headers, app
from apps.api.changetrace_api.security import Principal, authenticate_websocket
from changetrace_schemas import (
    AnalysisResult,
    ChangeDecision,
    ChangeIntent,
    CoverageStatus,
    DecisionStatus,
    Evidence,
    EvidenceStrength,
    EvidenceType,
    ImpactSummary,
    RepositoryCreate,
    Risk,
    RiskFactors,
    Severity,
    SourceLocation,
    SupportStatus,
)
from fastapi import HTTPException, Response
from infrastructure.migrations.runner import split_sql_statements
from services.github.checks import GitHubChecksService, _validate_pr_number, _validate_repo_full_name
from services.llm.client import OpenAICompatibleClient
from services.reporting.exporter import ReportExporter
from services.repository_analysis.analyzer import IndexedRepository, RepositoryAnalyzer
from services.retention.service import RetentionService, redact_credentials


def test_repo_root_fallback_rejected_in_production(monkeypatch):
    """Verify that in production, attempting to access files via repo_root fallback is strictly blocked."""
    prod_settings = Settings(
        environment="production",
        auth_mode="oauth",
        local_repository_root="/configured/empty/path",
        snapshot_storage_root="/var/snapshots",
        secret_key="a" * 32,
        session_secret="b" * 32,
        github_webhook_secret="c" * 32,
        session_cookie_secure=True,
    )
    monkeypatch.setattr("apps.api.changetrace_api.main.settings", prod_settings)
    with pytest.raises(ValueError, match="Repository path is outside configured repository roots"):
        _safe_local_path("pyproject.toml")


def test_repo_root_blocks_sensitive_env_files_in_dev(monkeypatch, tmp_path):
    """Verify that accessing .env configuration files is forbidden even in development mode."""
    dev_settings = Settings(
        environment="development",
        local_repository_root=str(tmp_path),
        snapshot_storage_root=str(tmp_path / "snaps"),
    )
    monkeypatch.setattr("apps.api.changetrace_api.main.settings", dev_settings)
    with pytest.raises(ValueError, match="Access to server configuration files is restricted"):
        _safe_local_path(".env")


def test_cors_allows_put_patch_methods():
    """Verify that CORS middleware explicitly permits PUT and PATCH methods."""
    from fastapi.middleware.cors import CORSMiddleware

    cors_middleware = next(
        m for m in app.user_middleware if m.cls == CORSMiddleware
    )
    allowed_methods = cors_middleware.kwargs["allow_methods"]
    assert "GET" in allowed_methods
    assert "POST" in allowed_methods
    assert "PUT" in allowed_methods
    assert "PATCH" in allowed_methods
    assert "DELETE" in allowed_methods
    assert "OPTIONS" in allowed_methods


def test_security_headers_include_hsts_and_permissions_policy(monkeypatch):
    """Verify that security headers include Permissions-Policy and Strict-Transport-Security."""
    resp = Response()
    _set_security_headers(resp, "test-request-id")
    assert resp.headers["x-request-id"] == "test-request-id"
    assert resp.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert resp.headers["x-content-type-options"] == "nosniff"

    # Test HSTS under production settings
    prod_settings = Settings(
        environment="production",
        auth_mode="oauth",
        session_cookie_secure=True,
        secret_key="a" * 32,
        session_secret="b" * 32,
        github_webhook_secret="c" * 32,
    )
    monkeypatch.setattr("apps.api.changetrace_api.main.settings", prod_settings)
    resp_prod = Response()
    _set_security_headers(resp_prod, "prod-req")
    assert "strict-transport-security" in resp_prod.headers
    assert "max-age=31536000" in resp_prod.headers["strict-transport-security"]


def test_websocket_rejects_invalid_roles():
    """Verify that authenticate_websocket rejects unauthorized/invalid roles."""
    mock_ws = MagicMock()
    mock_ws.cookies = {}
    mock_ws.query_params.get.return_value = None
    mock_ws.client.host = "127.0.0.1"
    mock_ws.headers = {
        "x-organization-id": str(uuid.uuid4()),
        "x-user-id": str(uuid.uuid4()),
        "x-role": "MALICIOUS_ROLE",
    }
    with pytest.raises(HTTPException) as exc:
        authenticate_websocket(mock_ws)
    assert exc.value.status_code == 403
    assert "Invalid role" in exc.value.detail


def test_websocket_accepts_valid_roles():
    """Verify that authenticate_websocket accepts valid RBAC roles in dev mode."""
    valid_roles = ["OWNER", "ADMIN", "MEMBER", "VIEWER"]
    for role in valid_roles:
        mock_ws = MagicMock()
        mock_ws.cookies = {}
        mock_ws.query_params.get.return_value = None
        mock_ws.client.host = "127.0.0.1"
        mock_ws.headers = {
            "x-organization-id": str(uuid.uuid4()),
            "x-user-id": str(uuid.uuid4()),
            "x-role": role,
        }
        principal = authenticate_websocket(mock_ws)
        assert principal.role == role


def test_credential_redaction_advanced_tokens_and_unquoted():
    """Verify that modern API keys (OpenAI, Slack, Anthropic) and unquoted secrets are redacted."""
    raw = (
        "OpenAI: sk-proj-1234567890abcdef1234567890\n"
        "Anthropic: sk-ant-api03-abcdef1234567890123456\n"
        "Slack: xoxb-1234567890-abcdef1234\n"
        "api_key = abcdef12345678901234\n"
        "password: secretpassword1234\n"
        "ghp_1234567890abcdef1234567890abcdef1234\n"
    )
    redacted = redact_credentials(raw)
    assert "sk-proj-" not in redacted
    assert "sk-ant-" not in redacted
    assert "xoxb-" not in redacted
    assert "secretpassword1234" not in redacted
    assert "abcdef12345678901234" not in redacted
    assert "[REDACTED]" in redacted


def test_retention_purge_directory_traversal_defense(tmp_path):
    """Verify that RetentionService prevents directory traversal during purge operations."""
    storage_root = tmp_path / "snapshots"
    storage_root.mkdir()
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "target.txt").write_text("must survive")

    service = RetentionService(storage_root=storage_root)
    mock_session = MagicMock()
    mock_session.get.return_value = MagicMock(id="../../outside_dir")
    mock_session.scalars.return_value.all.return_value = []

    # Attempt purge with directory traversal ID
    service.purge_repository(mock_session, "../../outside_dir")
    assert outside_dir.exists()
    assert (outside_dir / "target.txt").exists()


def test_llm_client_rejects_ssrf_and_invalid_schemes():
    """Verify that OpenAICompatibleClient validates base_url and blocks SSRF/metadata endpoints."""
    # Invalid scheme
    with pytest.raises(ValueError, match="Scheme must be http or https"):
        OpenAICompatibleClient("ftp://api.example.com", "key", "model")

    # File scheme
    with pytest.raises(ValueError, match="Scheme must be http or https"):
        OpenAICompatibleClient("file:///etc/passwd", "key", "model")

    # AWS metadata endpoint
    with pytest.raises(ValueError, match="cloud metadata services is forbidden"):
        OpenAICompatibleClient("http://169.254.169.254/latest/meta-data", "key", "model")

    # GCP metadata endpoint
    with pytest.raises(ValueError, match="cloud metadata services is forbidden"):
        OpenAICompatibleClient("http://metadata.google.internal/computeMetadata/v1", "key", "model")


def test_github_checks_rejects_path_traversal_in_repo_name():
    """Verify that GitHubChecksService validates repo_full_name against path traversal."""
    with pytest.raises(ValueError, match="Invalid repository full name"):
        _validate_repo_full_name("../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid repository full name"):
        _validate_repo_full_name("owner/repo/../../malicious")

    with pytest.raises(ValueError, match="Invalid PR number"):
        _validate_pr_number(-5)

    with pytest.raises(ValueError, match="Invalid PR number"):
        _validate_pr_number(0)

    # Valid check
    assert _validate_repo_full_name("valid-org/valid-repo") == "valid-org/valid-repo"
    assert _validate_pr_number(42) == 42


def test_repository_create_rejects_unsafe_branch_and_github_url():
    """Verify that RepositoryCreate validates branch names and GitHub URLs."""
    # Command flag branch injection
    with pytest.raises(ValueError, match="default_branch contains unsafe characters"):
        RepositoryCreate(name="test", default_branch="--upload-pack=evil")

    with pytest.raises(ValueError, match="default_branch contains unsafe characters"):
        RepositoryCreate(name="test", default_branch="branch;rm -rf /")

    # Insecure or malformed GitHub URLs
    with pytest.raises(ValueError, match="must be a valid HTTPS GitHub repository URL"):
        RepositoryCreate(name="test", github_url="http://github.com/insecure/repo")

    with pytest.raises(ValueError, match="must be a valid HTTPS GitHub repository URL"):
        RepositoryCreate(name="test", github_url="https://evil.com/owner/repo")

    # Valid repository creation
    valid = RepositoryCreate(
        name="test",
        default_branch="release/v1.0.0",
        github_url="https://github.com/valid-org/valid-repo",
    )
    assert valid.default_branch == "release/v1.0.0"


def test_python_analyzer_catches_deep_recursion_without_crashing(tmp_path):
    """Verify that the repository analyzer handles malformed or deeply nested code gracefully."""
    analyzer = RepositoryAnalyzer(use_treesitter=False)
    index = IndexedRepository(
        root=tmp_path,
        snapshot_id="snap-test",
        commit_sha="sha123",
    )
    # Deeply nested code that causes recursion limit or syntax error
    deep_code = "(" * 500 + ")" * 500
    analyzer._parse_python(index, "nested.py", deep_code)
    # Must not raise unhandled exception, instead records parse warning
    assert len(index.parse_warnings) >= 1
    assert "Python parse failure" in index.parse_warnings[0]


def test_report_exporter_sanitizes_html_script_tags():
    """Verify that ReportExporter.markdown escapes raw HTML and script tags."""
    dummy_result = AnalysisResult(
        repository="<script>alert('xss')</script>",
        commit_sha="a" * 40,
        snapshot_id="snap-123",
        analyzer_version="0.2.0",
        model_version="test",
        change_request="<img src=x onerror=alert(1)>",
        intent=ChangeIntent(entities=[], actions=[]),
        impact_summary=ImpactSummary(),
        components=[],
        graph_edges=[],
        evidence=[],
        business_rules=[],
        risks=[
            Risk(
                risk_id="R-1",
                title="<svg onload=alert(2)>",
                severity=Severity.HIGH,
                risk_score=80,
                confidence=0.9,
                claim="<b>Unsafe</b>",
                reasoning="test",
                evidence=["E-1"],
                affected_components=["C-1"],
                recommended_action="<script>steal()</script>",
                factors=RiskFactors(
                    dependency_impact=5.0,
                    business_criticality=5.0,
                    test_gap=5.0,
                    integration_exposure=5.0,
                    ambiguity=5.0,
                ),
                support_status=SupportStatus.SUPPORTED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
        test_gaps=[],
        change_plan=[],
        decision=ChangeDecision(status=DecisionStatus.GO, rationale=[], required_actions=[]),
    )
    markdown = ReportExporter.markdown(dummy_result)
    assert "<script>" not in markdown
    assert "<img" not in markdown
    assert "<svg" not in markdown
    assert "&lt;script&gt;alert('xss')&lt;/script&gt;" in markdown
    assert "&lt;img src=x onerror=alert(1)&gt;" in markdown


def test_docker_compose_and_nginx_security_configurations():
    """Verify that docker-compose binds web to localhost and nginx.conf has security headers."""
    compose_path = Path("docker-compose.yml")
    compose_text = compose_path.read_text(encoding="utf-8")
    assert 'ports: ["127.0.0.1:5173:80"]' in compose_text

    nginx_path = Path("frontend/nginx.conf") if Path("frontend/nginx.conf").exists() else Path("infrastructure/docker/nginx.conf")
    nginx_text = nginx_path.read_text(encoding="utf-8")
    assert "server_tokens off;" in nginx_text
    assert 'proxy_set_header Upgrade $http_upgrade;' in nginx_text
    assert 'proxy_set_header Connection "upgrade";' in nginx_text
    assert 'add_header Referrer-Policy "no-referrer" always;' in nginx_text
    assert 'add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;' in nginx_text


def test_migration_007_defines_rls_for_snapshots_evidence_and_artifacts():
    """Verify that migration 007 enables RLS for repository_snapshots, evidence, and analysis_artifacts."""
    mig_path = Path("backend/infrastructure/migrations/versions/007_row_level_security_artifacts_evidence.sql") if Path("backend/infrastructure/migrations/versions/007_row_level_security_artifacts_evidence.sql").exists() else Path("infrastructure/migrations/versions/007_row_level_security_artifacts_evidence.sql")
    content = mig_path.read_text(encoding="utf-8")
    stmts = split_sql_statements(content)
    alter_stmts = [s for s in stmts if s.startswith("ALTER TABLE")]
    assert len(alter_stmts) == 3
    assert any("repository_snapshots ENABLE ROW LEVEL SECURITY" in s for s in alter_stmts)
    assert any("evidence ENABLE ROW LEVEL SECURITY" in s for s in alter_stmts)
    assert any("analysis_artifacts ENABLE ROW LEVEL SECURITY" in s for s in alter_stmts)

    do_stmt = [s for s in stmts if s.startswith("DO $$")][0]
    assert "tenant_isolation_snapshots" in do_stmt
    assert "tenant_isolation_evidence" in do_stmt
    assert "tenant_isolation_analysis_artifacts" in do_stmt
