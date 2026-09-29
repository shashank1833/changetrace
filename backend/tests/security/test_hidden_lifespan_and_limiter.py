from unittest.mock import MagicMock
import pytest
from apps.api.changetrace_api.config import get_settings
from apps.api.changetrace_api.main import lifespan, app
from apps.api.changetrace_api.database import SessionLocal, create_schema
from apps.api.changetrace_api.models import Organization, User


@pytest.mark.asyncio
async def test_production_lifespan_does_not_seed_dev_org():
    settings = get_settings()
    orig_env = settings.environment
    orig_auth = settings.auth_mode
    try:
        settings.environment = "production"
        settings.auth_mode = "github"
        
        # Clear dev user/org if present
        create_schema()
        with SessionLocal() as session:
            dev_u = session.get(User, "00000000-0000-0000-0000-000000000001")
            if dev_u:
                session.delete(dev_u)
            dev_o = session.get(Organization, "00000000-0000-0000-0000-000000000001")
            if dev_o:
                session.delete(dev_o)
            session.commit()

        # Run lifespan in production mode
        async with lifespan(app):
            pass

        # Verify dev org was NOT seeded
        with SessionLocal() as session:
            assert session.get(Organization, "00000000-0000-0000-0000-000000000001") is None
            assert session.get(User, "00000000-0000-0000-0000-000000000001") is None
    finally:
        settings.environment = orig_env
        settings.auth_mode = orig_auth
