from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from changetrace_schemas import (
    AnalysisResult,
    AnalysisStatus,
    ChangeCreate,
    FindingFeedbackCreate,
    JobView,
    RepositoryCreate,
)
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.reporting import ReportExporter
from workers.analysis import AnalysisPipeline

from .config import get_settings
from .database import SessionLocal, create_schema, get_session
from .models import (
    AnalysisJob,
    AnalysisRun,
    AuditLog,
    ChangeRequest,
    EvidenceRecord,
    FindingFeedback,
    Organization,
    Repository,
    RepositorySnapshot,
)
from .security import Principal, current_principal, require_write

settings = get_settings()
logger = logging.getLogger("changetrace.api")
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_schema()
    with SessionLocal() as session:
        org_id = "00000000-0000-0000-0000-000000000001"
        if session.get(Organization, org_id) is None:
            session.add(Organization(id=org_id, name="Development Organization"))
            session.commit()
    yield


app = FastAPI(title="ChangeTrace API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID", "X-User-ID", "X-Organization-ID", "X-Role"],
)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:  # Optional in minimal contributor environments.
    logger.warning("opentelemetry_instrumentation_unavailable")


@app.middleware("http")
async def secure_and_trace(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started = time.perf_counter()
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rate_lock:
        window = _rate_windows[client_key]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            response = JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
            _set_security_headers(response, request_id)
            return response
        window.append(now)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id, "path": request.url.path})
        raise
    _set_security_headers(response, request_id)
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


def _set_security_headers(response, request_id: str) -> None:
    response.headers["x-request-id"] = request_id
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["x-frame-options"] = "DENY"
    response.headers["referrer-policy"] = "no-referrer"
    response.headers["content-security-policy"] = "default-src 'self'"


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


def _tenant_get(session: Session, model, resource_id: str, principal: Principal):
    item = session.scalar(
        select(model).where(model.id == resource_id, model.organization_id == str(principal.organization_id))
    )
    if item is None:
        raise HTTPException(404, "Resource not found")
    return item


def _audit(session: Session, principal: Principal, action: str, resource_type: str, resource_id: str):
    session.add(
        AuditLog(
            organization_id=str(principal.organization_id),
            actor_id=str(principal.user_id),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    )


@app.post("/api/v1/repositories", status_code=201)
def create_repository(
    payload: RepositoryCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(current_principal),
):
    require_write(principal)
    if not payload.source_path and not payload.github_url:
        raise HTTPException(422, "source_path or github_url is required")
    repository = Repository(
        id=str(uuid.uuid4()), organization_id=str(principal.organization_id), **payload.model_dump()
    )
    session.add(repository)
    _audit(session, principal, "repository.create", "repository", repository.id)
    session.commit()
    return _repository_view(repository)


@app.get("/api/v1/repositories")
def list_repositories(session: Session = Depends(get_session), principal: Principal = Depends(current_principal)):
    items = session.scalars(
        select(Repository).where(Repository.organization_id == str(principal.organization_id))
    ).all()
    return [_repository_view(item) for item in items]


@app.get("/api/v1/repositories/{repository_id}")
def get_repository(
    repository_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    return _repository_view(_tenant_get(session, Repository, str(repository_id), principal))


@app.post("/api/v1/repositories/{repository_id}/sync", status_code=202)
def sync_repository(
    repository_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    require_write(principal)
    repo = _tenant_get(session, Repository, str(repository_id), principal)
    from services.repository_analysis import SnapshotService

    if repo.source_path:
        snapshot = SnapshotService().from_local(_safe_local_path(repo.source_path))
    elif repo.github_url:
        snapshot = SnapshotService().clone_github(repo.github_url, workspace_root=_snapshot_storage_root())
        repo.source_path = str(snapshot.path)
    else:
        raise HTTPException(422, "Repository has no source")
    if session.get(RepositorySnapshot, snapshot.id) is None:
        session.add(
            RepositorySnapshot(
                id=snapshot.id,
                repository_id=repo.id,
                commit_sha=snapshot.commit_sha,
                version="0.1.0",
                status="VALID",
            )
        )
    _audit(session, principal, "repository.sync", "repository", repo.id)
    session.commit()
    return {"snapshot_id": snapshot.id, "commit_sha": snapshot.commit_sha, "status": "INDEXABLE"}


@app.post("/api/v1/changes", status_code=201)
def create_change(
    payload: ChangeCreate, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    require_write(principal)
    _tenant_get(session, Repository, str(payload.repository_id), principal)
    change = ChangeRequest(
        id=str(uuid.uuid4()),
        organization_id=str(principal.organization_id),
        repository_id=str(payload.repository_id),
        description=payload.description,
        proposed_diff=payload.proposed_diff,
        base_ref=payload.base_ref,
        target_ref=payload.target_ref,
    )
    session.add(change)
    _audit(session, principal, "change.create", "change_request", change.id)
    session.commit()
    return _change_view(change)


@app.get("/api/v1/changes")
def list_changes(session: Session = Depends(get_session), principal: Principal = Depends(current_principal)):
    items = session.scalars(
        select(ChangeRequest).where(ChangeRequest.organization_id == str(principal.organization_id))
    ).all()
    return [_change_view(item) for item in items]


@app.get("/api/v1/changes/{change_id}")
def get_change(
    change_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    return _change_view(_tenant_get(session, ChangeRequest, str(change_id), principal))


@app.post("/api/v1/changes/{change_id}/analyze", response_model=JobView, status_code=202)
def analyze_change(
    change_id: uuid.UUID,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    principal: Principal = Depends(current_principal),
):
    require_write(principal)
    change = _tenant_get(session, ChangeRequest, str(change_id), principal)
    job = AnalysisJob(
        id=str(uuid.uuid4()),
        organization_id=str(principal.organization_id),
        change_request_id=change.id,
        status=AnalysisStatus.QUEUED.value,
        progress="0",
    )
    session.add(job)
    _audit(session, principal, "analysis.queue", "analysis_job", job.id)
    session.commit()
    if settings.queue_mode == "redis":
        from redis import Redis
        from rq import Queue, Retry

        queue = Queue("changetrace", connection=Redis.from_url(settings.redis_url))
        queue.enqueue(_run_analysis_job, job.id, retry=Retry(max=2, interval=[10, 30]))
    else:
        # Inline background execution keeps contributor setup credential-free.
        background.add_task(_run_analysis_job, job.id)
    return _job_view(job)


def _run_analysis_job(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(AnalysisJob, job_id)
        if not job:
            return
        try:
            job.status, job.progress = AnalysisStatus.INGESTING.value, "10"
            session.commit()
            change = session.get(ChangeRequest, job.change_request_id)
            repository = session.get(Repository, change.repository_id) if change else None
            if not change or not repository:
                raise ValueError("Analysis repository was not found")
            if not repository.source_path and repository.github_url:
                from services.repository_analysis import SnapshotService

                cloned = SnapshotService().clone_github(repository.github_url, workspace_root=_snapshot_storage_root())
                repository.source_path = str(cloned.path)
                session.commit()
            if not repository.source_path:
                raise ValueError("Analysis requires an accessible repository snapshot")
            job.status, job.progress = AnalysisStatus.PARSING.value, "25"
            session.commit()
            result = AnalysisPipeline().run(
                _safe_local_path(repository.source_path),
                change.description,
                proposed_diff=change.proposed_diff,
                base_ref=change.base_ref,
                target_ref=change.target_ref,
                repository_id=repository.id,
            )
            job.status, job.progress = AnalysisStatus.VERIFICATION.value, "90"
            session.commit()
            if session.get(RepositorySnapshot, result.snapshot_id) is None:
                session.add(
                    RepositorySnapshot(
                        id=result.snapshot_id,
                        repository_id=repository.id,
                        commit_sha=result.commit_sha,
                        version=result.analyzer_version,
                        status="VALID",
                    )
                )
            run = AnalysisRun(
                id=str(result.analysis_id),
                organization_id=job.organization_id,
                change_request_id=change.id,
                snapshot_id=result.snapshot_id,
                commit_sha=result.commit_sha,
                analyzer_version=result.analyzer_version,
                model_version=result.model_version,
                result=result.model_dump(mode="json"),
            )
            session.add(run)
            for evidence in result.evidence:
                if session.get(EvidenceRecord, evidence.id) is None:
                    session.add(
                        EvidenceRecord(
                            id=evidence.id,
                            repository_snapshot_id=evidence.repository_snapshot_id,
                            type=evidence.type.value,
                            file=evidence.location.file,
                            line_start=str(evidence.location.line_start),
                            line_end=str(evidence.location.line_end),
                            content_hash=evidence.content_hash,
                            payload=evidence.model_dump(mode="json"),
                        )
                    )
            job.analysis_id, job.status, job.progress = run.id, AnalysisStatus.COMPLETED.value, "100"
            change.status = "ANALYZED"
            session.commit()
        except Exception:
            session.rollback()
            job = session.get(AnalysisJob, job_id)
            if job:
                job.status, job.error = (
                    AnalysisStatus.FAILED.value,
                    "Analysis failed; consult server logs with the job ID",
                )
                session.commit()
            logger.exception("analysis_failed", extra={"job_id": job_id})


@app.get("/api/v1/analyses/{analysis_id}")
def get_analysis(
    analysis_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    run = _tenant_get(session, AnalysisRun, str(analysis_id), principal)
    return run.result


@app.get("/api/v1/analyses/{analysis_id}/status")
def analysis_status(
    analysis_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    run = _tenant_get(session, AnalysisRun, str(analysis_id), principal)
    return {"analysis_id": run.id, "status": "COMPLETED", "progress": 100}


@app.get("/api/v1/jobs/{job_id}", response_model=JobView)
def job_status(
    job_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    return _job_view(_tenant_get(session, AnalysisJob, str(job_id), principal))


@app.websocket("/api/v1/jobs/{job_id}/events")
async def job_events(websocket: WebSocket, job_id: str):
    try:
        organization_id = uuid.UUID(websocket.headers.get("x-organization-id", "00000000-0000-0000-0000-000000000001"))
    except ValueError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    for _ in range(120):
        with SessionLocal() as session:
            job = session.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.id == job_id,
                    AnalysisJob.organization_id == str(organization_id),
                )
            )
            if not job:
                await websocket.send_json({"error": "not found"})
                break
            await websocket.send_json(_job_view(job).model_dump(mode="json"))
            if job.status in {AnalysisStatus.COMPLETED.value, AnalysisStatus.FAILED.value}:
                break
        await asyncio.sleep(1)
    await websocket.close()


def _result_for_change(change_id: str, session: Session, principal: Principal) -> AnalysisResult:
    _tenant_get(session, ChangeRequest, change_id, principal)
    run = session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.change_request_id == change_id, AnalysisRun.organization_id == str(principal.organization_id)
        )
        .order_by(AnalysisRun.created_at.desc())
    )
    if not run:
        raise HTTPException(404, "No completed analysis for this change")
    return AnalysisResult.model_validate(run.result)


@app.get("/api/v1/changes/{change_id}/impact")
def impact(
    change_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    result = _result_for_change(str(change_id), session, principal)
    return {
        "summary": result.impact_summary,
        "components": result.components,
        "edges": result.graph_edges,
        "business_rules": result.business_rules,
    }


@app.get("/api/v1/changes/{change_id}/risks")
def risks(
    change_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    return _result_for_change(str(change_id), session, principal).risks


@app.get("/api/v1/risks/{risk_id}")
def risk(risk_id: str, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)):
    runs = session.scalars(
        select(AnalysisRun).where(AnalysisRun.organization_id == str(principal.organization_id))
    ).all()
    for run in runs:
        for item in run.result.get("risks", []):
            if item["risk_id"] == risk_id:
                return item
    raise HTTPException(404, "Risk not found")


@app.get("/api/v1/evidence/{evidence_id}")
def evidence(
    evidence_id: str, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    # Resolve through tenant-owned immutable analysis output. Evidence IDs are
    # content-derived and may be identical across organizations, so returning the
    # global cache row could disclose the repository_id stored by another tenant.
    runs = session.scalars(
        select(AnalysisRun).where(AnalysisRun.organization_id == str(principal.organization_id))
    ).all()
    for run in runs:
        for item in run.result.get("evidence", []):
            if item.get("id") == evidence_id:
                return item
    raise HTTPException(404, "Evidence not found")


@app.get("/api/v1/changes/{change_id}/test-gaps")
def test_gaps(
    change_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    return _result_for_change(str(change_id), session, principal).test_gaps


@app.get("/api/v1/analyses/{analysis_id}/report")
def export_report(
    analysis_id: uuid.UUID,
    format: str = "json",
    session: Session = Depends(get_session),
    principal: Principal = Depends(current_principal),
):
    run = _tenant_get(session, AnalysisRun, str(analysis_id), principal)
    result = AnalysisResult.model_validate(run.result)
    if format == "json":
        return result.model_dump(mode="json")
    if format != "markdown":
        raise HTTPException(422, "format must be json or markdown")
    return {"format": "markdown", "content": ReportExporter.markdown(result)}


@app.post("/api/v1/analyses/{analysis_id}/findings/{finding_id}/feedback", status_code=201)
def create_finding_feedback(
    analysis_id: uuid.UUID,
    finding_id: str,
    payload: FindingFeedbackCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(current_principal),
):
    require_write(principal)
    run = _tenant_get(session, AnalysisRun, str(analysis_id), principal)
    finding_ids = {item["risk_id"] for item in run.result.get("risks", [])}
    finding_ids.update(item["scenario_id"] for item in run.result.get("test_gaps", []))
    if finding_id not in finding_ids:
        raise HTTPException(404, "Finding not found")
    feedback = FindingFeedback(
        organization_id=str(principal.organization_id),
        analysis_id=run.id,
        finding_id=finding_id,
        user_id=str(principal.user_id),
        decision=payload.decision,
        reason=payload.reason,
        analyzer_version=run.analyzer_version,
    )
    session.add(feedback)
    _audit(session, principal, "finding.feedback", "finding", finding_id)
    session.commit()
    return {"id": feedback.id, "decision": feedback.decision, "created_at": feedback.created_at}


@app.get("/api/v1/changes/{change_id}/plan")
def plan(
    change_id: uuid.UUID, session: Session = Depends(get_session), principal: Principal = Depends(current_principal)
):
    return {"steps": _result_for_change(str(change_id), session, principal).change_plan}


def _snapshot_storage_root() -> Path:
    root = Path(settings.snapshot_storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_local_path(source_path: str) -> Path:
    path = Path(source_path).expanduser().resolve()
    allowed_roots = (
        Path(settings.local_repository_root).expanduser().resolve(),
        _snapshot_storage_root(),
    )
    if not any(path == root or root in path.parents for root in allowed_roots):
        raise ValueError("Repository path is outside configured repository roots")
    return path


def _repository_view(item: Repository) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "github_url": item.github_url,
        "source_path": item.source_path,
        "default_branch": item.default_branch,
        "created_at": item.created_at,
    }


def _change_view(item: ChangeRequest) -> dict:
    return {
        "id": item.id,
        "repository_id": item.repository_id,
        "description": item.description,
        "has_proposed_diff": bool(item.proposed_diff),
        "base_ref": item.base_ref,
        "target_ref": item.target_ref,
        "status": item.status,
        "created_at": item.created_at,
    }


def _job_view(job: AnalysisJob) -> JobView:
    return JobView(
        id=uuid.UUID(job.id),
        status=AnalysisStatus(job.status),
        progress=int(job.progress),
        analysis_id=uuid.UUID(job.analysis_id) if job.analysis_id else None,
        error=job.error,
    )
