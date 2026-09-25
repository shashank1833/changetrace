import uuid

import fakeredis
import pytest
from rq import Queue, SimpleWorker

from apps.api.changetrace_api.database import SessionLocal
from apps.api.changetrace_api.main import _run_analysis_job
from apps.api.changetrace_api.models import AnalysisJob, ChangeRequest, Organization, Repository


@pytest.mark.integration
def test_redis_rq_queue_and_worker_execution_fakeredis():
    fake_redis = fakeredis.FakeRedis()
    queue = Queue("changetrace", connection=fake_redis)

    uid = uuid.uuid4().hex[:8]
    job_id = f"job-rq-{uid}"
    repo_id = f"repo-rq-{uid}"
    change_id = f"change-rq-{uid}"

    with SessionLocal() as session:
        org = Organization(name=f"RQ Org {uid}")
        session.add(org)
        session.commit()

        repo = Repository(
            id=repo_id,
            organization_id=org.id,
            name="rq-test-repo",
            source_path="tests/evaluation/demo_repository",
        )
        change = ChangeRequest(
            id=change_id,
            organization_id=org.id,
            repository_id=repo.id,
            description="Add return status to order",
        )
        job = AnalysisJob(
            id=job_id,
            organization_id=org.id,
            change_request_id=change.id,
            status="QUEUED",
            progress="0",
        )
        session.add_all([repo, change, job])
        session.commit()

    # Enqueue job to Redis queue
    rq_job = queue.enqueue(_run_analysis_job, job_id)
    assert rq_job.id is not None

    # Execute worker burst against the Redis queue
    worker = SimpleWorker([queue], connection=fake_redis)
    worker.work(burst=True)

    # Verify execution outcome in database
    with SessionLocal() as session:
        db_job = session.get(AnalysisJob, job_id)
        assert db_job is not None
        assert db_job.status == "COMPLETED"
        assert db_job.progress == "100"
        assert db_job.analysis_id is not None


@pytest.mark.integration
def test_redis_rq_queue_and_worker_execution_real_redis():
    """Live integration test against a running Redis container."""
    import socket

    import redis

    try:
        s = socket.create_connection(("127.0.0.1", 6379), timeout=0.5)
        s.close()
    except (TimeoutError, ConnectionRefusedError, OSError):
        pytest.skip("Live Redis is not accessible on localhost:6379; skipping live Redis execution.")

    real_redis = redis.Redis.from_url("redis://127.0.0.1:6379/0")
    try:
        real_redis.ping()
    except Exception:
        pytest.skip("Could not ping live Redis on localhost:6379; skipping live Redis execution.")

    queue = Queue("changetrace-live-test", connection=real_redis)

    uid = uuid.uuid4().hex[:8]
    job_id = f"job-live-rq-{uid}"
    repo_id = f"repo-live-rq-{uid}"
    change_id = f"change-live-rq-{uid}"

    with SessionLocal() as session:
        org = Organization(name=f"Live RQ Org {uid}")
        session.add(org)
        session.commit()

        repo = Repository(
            id=repo_id,
            organization_id=org.id,
            name="rq-live-test-repo",
            source_path="tests/evaluation/demo_repository",
        )
        change = ChangeRequest(
            id=change_id,
            organization_id=org.id,
            repository_id=repo.id,
            description="Add return status to order",
        )
        job = AnalysisJob(
            id=job_id,
            organization_id=org.id,
            change_request_id=change.id,
            status="QUEUED",
            progress="0",
        )
        session.add_all([repo, change, job])
        session.commit()

    rq_job = queue.enqueue(_run_analysis_job, job_id)
    assert rq_job.id is not None

    worker = SimpleWorker([queue], connection=real_redis)
    worker.work(burst=True)

    with SessionLocal() as session:
        db_job = session.get(AnalysisJob, job_id)
        assert db_job is not None
        assert db_job.status == "COMPLETED"
        assert db_job.progress == "100"
        assert db_job.analysis_id is not None

