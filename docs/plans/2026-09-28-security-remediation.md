# ChangeTrace Security Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate all 12 identified security vulnerabilities and loopholes across authentication, path traversal, container infrastructure, denial-of-service, multi-tenant isolation, secrets handling, and feedback integrity.

**Architecture:** Harden API endpoints, request validators, database migrations, rate limiters, pipeline resource management, and Docker configurations. Preserve backwards compatibility for local developer evaluation while securing production and multi-tenant boundaries.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy 2.0, PostgreSQL (RLS), Redis, RQ, Docker Compose, Vitest / Pytest.

**Spec:** `SECURITY_AUDIT_REPORT.md`

## Global Constraints
- Do not break existing valid functionality or developer workflows for running local tests.
- All tests in `tests/` must continue to pass or be updated to adhere to hardened security boundaries.
- No secrets or private tokens in plain text in logs, Redis, command-line arguments, or exception messages.

---

### Task 1: Path Traversal & Host File Exposure Remediation (CT-SEC-02)
**Files:**
- Modify: `apps/api/changetrace_api/main.py:945-996`
- Test: `tests/security/test_path_traversal_hardening.py`

**Interfaces:**
- `_safe_local_path(source_path: str) -> Path` strictly verifies that resolved path resides inside `settings.local_repository_root` or `settings.snapshot_storage_root`.

- [ ] **Step 1: Write failing tests for arbitrary directory traversal attempts (`/etc`, `C:\Windows`, `.ssh`)**
- [ ] **Step 2: Remove the dangerous `if settings.environment == "development" and path.is_dir(): return path` bypass**
- [ ] **Step 3: Run the test to ensure arbitrary directory traversal is blocked with a 400 ValueError**

---

### Task 2: Authentication & WebSocket Header Spoofing Hardening (CT-SEC-01)
**Files:**
- Modify: `apps/api/changetrace_api/security.py:75-125`
- Test: `tests/security/test_auth_hardening.py`

**Interfaces:**
- `current_principal`: Disallow arbitrary headers unless explicitly in development AND originating from loopback / trusted local host; ensure production strictly rejects unauthenticated header spoofing.
- `authenticate_websocket`: Disallow token query parameter in production, authenticate via secure cookie or Authorization header.

- [ ] **Step 1: Write failing tests verifying header spoofing fails in non-dev or untrusted remote callers**
- [ ] **Step 2: Update `current_principal()` and `authenticate_websocket()` in `security.py`**
- [ ] **Step 3: Verify tests pass**

---

### Task 3: Sandbox CPU Limit Process-Termination Fix (CT-SEC-03)
**Files:**
- Modify: `services/repository_analysis/sandbox.py:51-65`
- Test: `tests/security/test_sandbox_limits.py`

**Interfaces:**
- `ParserSandbox.apply_process_limits()`: Remove process-wide `RLIMIT_CPU` that causes self-terminating servers; keep memory limit or handle CPU limits safely.

- [ ] **Step 1: Write test verifying `apply_process_limits` does not set destructive process-wide CPU limits**
- [ ] **Step 2: Modify `sandbox.py` to prevent server killing**
- [ ] **Step 3: Verify tests pass**

---

### Task 4: Pipeline Resource Cleanup & Temporary Directory Leaks (CT-SEC-11)
**Files:**
- Modify: `workers/analysis/pipeline.py:40-180`
- Test: `tests/security/test_pipeline_cleanup.py`

**Interfaces:**
- `AnalysisPipeline.run`: Wrap temporary directory lifecycle in `try ... finally` to ensure zero disk leaks upon analysis error.

- [ ] **Step 1: Write failing test that triggers pipeline error and asserts temporary directories are deleted**
- [ ] **Step 2: Refactor `AnalysisPipeline.run` with `try ... finally` blocks for `temporary` and `ref_temporary`**
- [ ] **Step 3: Verify test passes**

---

### Task 5: Evidence Query O(N×M) Algorithmic Memory Exhaustion Fix (CT-SEC-05)
**Files:**
- Modify: `apps/api/changetrace_api/main.py:769-785`
- Test: `tests/security/test_evidence_query.py`

**Interfaces:**
- `GET /api/v1/evidence/{evidence_id}`: Query `EvidenceRecord` table directly and verify organization ownership via `RepositorySnapshot` -> `Repository` relationship, avoiding full table scans into memory.

- [ ] **Step 1: Write test for single evidence lookup**
- [ ] **Step 2: Optimize endpoint to query `EvidenceRecord` directly with tenant validation**
- [ ] **Step 3: Verify test passes**

---

### Task 6: Docker Infrastructure Hardening (CT-SEC-04, CT-SEC-08)
**Files:**
- Modify: `docker-compose.yml`
- Modify: `infrastructure/docker/api.Dockerfile`

- [ ] **Step 1: In `docker-compose.yml`, bind ports `5432` and `6379` to `127.0.0.1` only**
- [ ] **Step 2: In `docker-compose.yml`, configure Redis with password authentication and update service URLs**
- [ ] **Step 3: In `infrastructure/docker/api.Dockerfile`, install `git` via `apt-get`**

---

### Task 7: PostgreSQL Row-Level Security (RLS) Enforcement (CT-SEC-06)
**Files:**
- Modify: `infrastructure/migrations/versions/004_row_level_security.sql`

- [ ] **Step 1: Add `FORCE ROW LEVEL SECURITY` statements to all tenant-scoped tables**
- [ ] **Step 2: Verify migration file syntax**

---

### Task 8: Webhook Replay & Unmapped Tenant Ingestion Protection (CT-SEC-09)
**Files:**
- Modify: `services/github/webhooks.py:215-245`
- Modify: `apps/api/changetrace_api/main.py:677-709`
- Test: `tests/security/test_webhook_hardening.py`

- [ ] **Step 1: Write test verifying unmapped installation in webhook is rejected**
- [ ] **Step 2: Remove arbitrary fallback to `Organization.limit(1)` in webhook handler**
- [ ] **Step 3: Verify tests pass**

---

### Task 9: Rate Limiter & Reverse Proxy IP Handling (CT-SEC-10)
**Files:**
- Modify: `apps/api/changetrace_api/main.py:89-115`
- Modify: `apps/api/changetrace_api/rate_limiter.py`
- Test: `tests/security/test_rate_limiter_hardening.py`

- [ ] **Step 1: Add cleanup/TTL eviction to `DistributedRateLimiter._local_windows`**
- [ ] **Step 2: Extract real client IP with `X-Forwarded-For` support**
- [ ] **Step 3: Verify tests pass**

---

### Task 10: Secrets in Process Table / Subprocess Git Hardening (CT-SEC-07)
**Files:**
- Modify: `services/repository_analysis/snapshot.py:31-53`
- Test: `tests/security/test_git_secret_leak.py`

- [ ] **Step 1: Pass GitHub token via `git -c http.extraHeader` rather than URL parameter**
- [ ] **Step 2: Verify git clone URL doesn't leak token in command args**

---

### Task 11: Feedback Decision Contract Normalization (CT-SEC-12)
**Files:**
- Modify: `apps/api/changetrace_api/main.py:850-895`
- Modify: `apps/web/src/App.tsx:170`
- Test: `tests/security/test_feedback_decision.py`

- [ ] **Step 1: Normalize `"CONFIRM"` to `"ACCEPTED"` in feedback metrics and creation**
- [ ] **Step 2: Align web UI button values**
- [ ] **Step 3: Verify tests pass**

---

### Task 12: Full Regression & Security Verification
- [ ] **Run all security unit and integration tests**
- [ ] **Run full project test suite (`pytest`)**
- [ ] **Verify no regressions**
