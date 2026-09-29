import uuid
from fastapi.testclient import TestClient
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.database import SessionLocal
from apps.api.changetrace_api.models import AnalysisRun, Organization, User


def test_feedback_confirm_is_treated_as_accepted():
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    analysis_id = str(uuid.uuid4())

    with SessionLocal() as session:
        session.add(Organization(id=org_id, name="Test Feedback Org"))
        session.add(User(id=user_id, organization_id=org_id, email="test@test.local", role="OWNER"))
        session.add(
            AnalysisRun(
                id=analysis_id,
                organization_id=org_id,
                change_request_id=str(uuid.uuid4()),
                snapshot_id="snap-1234",
                commit_sha="commit-1234",
                analyzer_version="0.2.0",
                model_version="test",
                result={
                    "risks": [{"risk_id": "R-1", "severity": "HIGH"}],
                    "test_gaps": [],
                },
            )
        )
        session.commit()

    client = TestClient(app)
    headers = {"X-Organization-ID": org_id, "X-User-ID": user_id, "X-Role": "OWNER"}

    # Post CONFIRM feedback
    resp = client.post(
        f"/api/v1/analyses/{analysis_id}/findings/R-1/feedback",
        headers=headers,
        json={"decision": "CONFIRM", "reason": "Accurate finding"},
    )
    assert resp.status_code == 201
    assert resp.json()["decision"] == "ACCEPTED"

    # Query metrics
    metrics_resp = client.get("/api/v1/feedback/metrics", headers=headers)
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["accepted_count"] >= 1
