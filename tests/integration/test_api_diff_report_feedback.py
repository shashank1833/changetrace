from pathlib import Path

from changetrace_api.main import app
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_api_persists_diff_exports_report_and_accepts_feedback(monkeypatch, tmp_path):
    import changetrace_api.main as main

    monkeypatch.setattr(main.settings, "local_repository_root", str(FIXTURE.parents[2]))
    monkeypatch.setattr(main.settings, "database_url", f"sqlite:///{tmp_path / 'unused.db'}")
    patch = """diff --git a/backend/models/order.py b/backend/models/order.py
--- a/backend/models/order.py
+++ b/backend/models/order.py
@@ -7,2 +7,3 @@ class OrderStatus(str, Enum):
     SHIPPED = "SHIPPED"
+    RETURNED = "RETURNED"
     CANCELLED = "CANCELLED"
"""
    with TestClient(app) as client:
        repository = client.post(
            "/api/v1/repositories",
            json={
                "name": "diff-demo",
                "source_path": str(FIXTURE.resolve()),
                "default_branch": "main",
            },
        ).json()
        change = client.post(
            "/api/v1/changes",
            json={
                "repository_id": repository["id"],
                "description": "Add RETURNED after SHIPPED.",
                "proposed_diff": patch,
            },
        ).json()
        job = client.post(f"/api/v1/changes/{change['id']}/analyze").json()
        completed = client.get(f"/api/v1/jobs/{job['id']}").json()
        assert completed["status"] == "COMPLETED"
        analysis = client.get(f"/api/v1/analyses/{completed['analysis_id']}").json()
        assert analysis["change_set"]["files"][0]["state_changes"][0]["value"] == "RETURNED"
        report = client.get(f"/api/v1/analyses/{completed['analysis_id']}/report?format=markdown")
        assert report.status_code == 200
        assert "ChangeTrace report" in report.json()["content"]
        risk_id = analysis["risks"][0]["risk_id"]
        feedback = client.post(
            f"/api/v1/analyses/{completed['analysis_id']}/findings/{risk_id}/feedback",
            json={"decision": "CONFIRM", "reason": "Verified by reviewer"},
        )
        assert feedback.status_code == 201
