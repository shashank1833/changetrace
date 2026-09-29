import uuid
import pytest
from starlette.testclient import TestClient
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.database import SessionLocal, create_schema
from apps.api.changetrace_api.models import Organization, Repository, RepositorySnapshot, EvidenceRecord
from services.retention.service import RetentionService


@pytest.fixture(autouse=True)
def init_db():
    create_schema()


def test_multitenant_evidence_collision_prevention():
    client = TestClient(app)
    
    org1_id = str(uuid.uuid4())
    org2_id = str(uuid.uuid4())
    repo1_id = str(uuid.uuid4())
    repo2_id = str(uuid.uuid4())
    snap1_id = f"snap-{uuid.uuid4().hex[:12]}"
    snap2_id = f"snap-{uuid.uuid4().hex[:12]}"
    shared_ev_id = "evid-shared-12345"

    with SessionLocal() as session:
        org1 = Organization(id=org1_id, name="Org 1")
        org2 = Organization(id=org2_id, name="Org 2")
        repo1 = Repository(id=repo1_id, organization_id=org1_id, name="Repo 1", default_branch="main")
        repo2 = Repository(id=repo2_id, organization_id=org2_id, name="Repo 2", default_branch="main")
        snap1 = RepositorySnapshot(id=snap1_id, repository_id=repo1_id, commit_sha="a" * 40, version="0.1.0", status="VALID")
        snap2 = RepositorySnapshot(id=snap2_id, repository_id=repo2_id, commit_sha="b" * 40, version="0.1.0", status="VALID")
        
        # Org 1 has evidence with shared_ev_id
        ev1 = EvidenceRecord(
            id=shared_ev_id,
            repository_snapshot_id=snap1_id,
            type="CODE_REFERENCE",
            file="app.py",
            line_start="1",
            line_end="5",
            content_hash="hash1",
            payload={"id": shared_ev_id, "snippet": "org 1 snippet"},
        )
        # Org 2 has evidence with scoped ID
        ev2 = EvidenceRecord(
            id=f"{snap2_id}:{shared_ev_id}",
            repository_snapshot_id=snap2_id,
            type="CODE_REFERENCE",
            file="app.py",
            line_start="1",
            line_end="5",
            content_hash="hash1",
            payload={"id": shared_ev_id, "snippet": "org 2 snippet"},
        )
        session.add_all([org1, org2, repo1, repo2, snap1, snap2, ev1, ev2])
        session.commit()

    # Query evidence as Org 1
    resp1 = client.get(
        f"/api/v1/evidence/{shared_ev_id}",
        headers={"x-organization-id": org1_id, "x-role": "OWNER"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["snippet"] == "org 1 snippet"

    # Query evidence as Org 2
    resp2 = client.get(
        f"/api/v1/evidence/{shared_ev_id}",
        headers={"x-organization-id": org2_id, "x-role": "OWNER"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["snippet"] == "org 2 snippet"

    # Delete Org 1's repository
    retention = RetentionService()
    with SessionLocal() as session:
        retention.purge_repository(session, repo1_id)

    # Org 2's evidence should still be accessible and not deleted
    resp2_after = client.get(
        f"/api/v1/evidence/{shared_ev_id}",
        headers={"x-organization-id": org2_id, "x-role": "OWNER"},
    )
    assert resp2_after.status_code == 200
    assert resp2_after.json()["snippet"] == "org 2 snippet"
