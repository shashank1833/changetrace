import pytest
from apps.api.changetrace_api.config import Settings


def test_production_rejects_default_session_secret():
    with pytest.raises(ValueError) as exc_info:
        Settings(environment="production", session_secret="change-me-in-production")
    assert "CHANGETRACE_SESSION_SECRET must be configured" in str(exc_info.value)


def test_production_accepts_configured_session_secret():
    settings = Settings(
        environment="production",
        session_secret="secure_random_production_secret_key_123",
        auth_mode="oauth",
        session_cookie_secure=True,
    )
    assert settings.environment == "production"
    assert settings.session_secret == "secure_random_production_secret_key_123"
