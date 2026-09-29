import uuid
from fastapi.testclient import TestClient
from apps.api.changetrace_api.main import app
from apps.api.changetrace_api.database import SessionLocal
from apps.api.changetrace_api.models import Repository, RepositorySnapshot, EvidenceRecord


def test_evidence_indexed_lookup():
    client = TestClient(app)
    org_id = str(uuid.uuid4())
    repo_id = str(uuid.uuid4())
    snap_id = f"snap-{uuid.uuid4().hex[:12]}"
    ev_id = f"E-{uuid.uuid4().hex[:12]}"
    
    with SessionLocal() as session:
        session.add(Repository(id=repo_id, organization_id=org_id, name="test-repo"))
        session.add(RepositorySnapshot(id=snap_id, repository_id=repo_id, commit_sha="abcdef123456", version="0.1.0"))
        session.add(
            EvidenceRecord(
                id=ev_id,
                repository_snapshot_id=snap_id,
                type="CODE_REFERENCE",
                file="test.py",
                line_start="1",
                line_end="5",
                content_hash="dummy-hash",
                payload={"id": ev_id, "file": "test.py", "snippet": "print('hello')"},
            )
        )
        session.commit()

    headers = {"X-Organization-ID": org_id, "X-User-ID": str(uuid.uuid4()), "X-Role": "OWNER"}
    
    # Matching tenant should find it via indexed query
    resp = client.get(f"/api/v1/evidence/{ev_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == ev_id

    # Cross-tenant caller must NOT find it
    other_headers = {"X-Organization-ID": str(uuid.uuid4()), "X-User-ID": str(uuid.uuid4()), "X-Role": "OWNER"}
    cross_resp = client.get(f"/api/v1/evidence/{ev_id}", headers=other_headers)
    assert cross_resp.status_code == 404
