from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.changetrace_api.database import get_session
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.models import (
    Base,
    FindingFeedback,
    Organization,
    User,
)
from apps.api.changetrace_api.security import Principal, current_principal


def test_feedback_metrics_and_summary_api(tmp_path):
    test_db = tmp_path / "test_feedback_api.db"
    engine = create_engine(f"sqlite:///{test_db}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    principal = Principal(organization_id=uuid.UUID(int=1), user_id=uuid.UUID(int=2), role="ADMIN")
    org_id_str = str(principal.organization_id)
    user_id_str = str(principal.user_id)

    with TestingSession() as session:
        session.add(Organization(id=org_id_str, name="Test Org"))
        session.add(User(id=user_id_str, organization_id=org_id_str, email="test@test.com", role="ADMIN"))
        session.add(FindingFeedback(
            id="fb-1",
            organization_id=org_id_str,
            analysis_id="run-1",
            finding_id="risk-1",
            user_id=user_id_str,
            decision="ACCEPTED",
            reason=None,
            analyzer_version="0.1.0",
        ))
        session.add(FindingFeedback(
            id="fb-2",
            organization_id=org_id_str,
            analysis_id="run-1",
            finding_id="risk-2",
            user_id=user_id_str,
            decision="REJECTED",
            reason="Noise in dead code",
            analyzer_version="0.1.0",
        ))
        session.commit()

    def override_session():
        with TestingSession() as session:
            yield session

    def override_principal():
        return principal

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_principal] = override_principal

    try:
        client = TestClient(app)
        res_m = client.get("/api/v1/feedback/metrics")
        assert res_m.status_code == 200
        data_m = res_m.json()
        assert data_m["total_feedback_count"] == 2
        assert data_m["accepted_count"] == 1
        assert data_m["rejected_count"] == 1
        assert data_m["overall_precision"] == 0.5
        assert "0.1.0" in data_m["precision_by_version"]

        res_s = client.get("/api/v1/feedback/summary")
        assert res_s.status_code == 200
        data_s = res_s.json()
        assert "Noise in dead code" in data_s["rejection_reasons"]
    finally:
        app.dependency_overrides.clear()
