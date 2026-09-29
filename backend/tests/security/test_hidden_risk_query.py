import uuid
import pytest
from starlette.testclient import TestClient
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.database import SessionLocal, create_schema
from apps.api.changetrace_api.models import Organization, ChangeRequest, Repository, AnalysisRun


@pytest.fixture(autouse=True)
def init_db():
    create_schema()


def test_bounded_risk_query():
    client = TestClient(app)
    org_id = str(uuid.uuid4())
    repo_id = str(uuid.uuid4())
    cr_id = str(uuid.uuid4())
    risk_id = "risk-high-priority"

    with SessionLocal() as session:
        org = Organization(id=org_id, name="Risk Org")
        repo = Repository(id=repo_id, organization_id=org_id, name="Risk Repo", default_branch="main")
        cr = ChangeRequest(id=cr_id, organization_id=org_id, repository_id=repo_id, description="Risk test CR")
        run = AnalysisRun(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            change_request_id=cr_id,
            snapshot_id="snap-1",
            commit_sha="a" * 40,
            analyzer_version="0.1.0",
            model_version="test",
            result={"risks": [{"risk_id": risk_id, "title": "Critical Payment Bug", "severity": "HIGH"}]},
        )
        session.add_all([org, repo, cr, run])
        session.commit()

    resp = client.get(
        f"/api/v1/risks/{risk_id}",
        headers={"x-organization-id": org_id, "x-role": "OWNER"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Critical Payment Bug"

    # Querying nonexistent risk returns 404 cleanly
    resp_404 = client.get(
        "/api/v1/risks/nonexistent-risk",
        headers={"x-organization-id": org_id, "x-role": "OWNER"},
    )
    assert resp_404.status_code == 404
