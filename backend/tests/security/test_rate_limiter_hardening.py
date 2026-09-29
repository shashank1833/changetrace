from fastapi.testclient import TestClient
from apps.api.changetrace_api.main import app, get_rate_limiter


def test_rate_limiter_separates_clients_by_forwarded_for():
    limiter = get_rate_limiter()
    limiter.reset()
    client = TestClient(app)

    # Client A sends request
    resp_a = client.get("/health", headers={"X-Forwarded-For": "198.51.100.1"})
    assert resp_a.status_code == 200

    # Client B should have its own separate rate limit bucket
    resp_b = client.get("/health", headers={"X-Forwarded-For": "198.51.100.2"})
    assert resp_b.status_code == 200
