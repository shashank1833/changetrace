# Implementation Plan - Remediation of 9 Hidden Security Vulnerabilities

**Objective:** Patch all 9 newly identified hidden security vulnerabilities across authentication, multi-tenant state isolation, schema validation, RLS, memory exhaustion, rate-limiting, and configuration hardening while leveraging standard libraries where code can be simplified.

---

### Tasks

1. **CT-HIDDEN-01: Header Auth Loopback Check Hardening**
   - **File:** `apps/api/changetrace_api/security.py`
   - **Change:** In `current_principal()` and `authenticate_websocket()`, use `ipaddress.ip_address` or direct host comparison on `request.client.host` only. Do NOT allow `X-Forwarded-For` to bypass the loopback check.
   - **Test:** `tests/security/test_hidden_auth_spoofing.py`

2. **CT-HIDDEN-02: Multi-Tenant Scoping for EvidenceRecord**
   - **Files:** `apps/api/changetrace_api/main.py`, `apps/api/changetrace_api/models.py`, `services/retention/service.py`
   - **Change:**
     - Prefix `EvidenceRecord.id` with repository snapshot ID or repo scope so records from different repos/tenants do not collide or overwrite each other.
     - Add `organization_id` foreign key to `EvidenceRecord` or scope by `repository_snapshot_id`.
     - In `main.py#_run_analysis_job`, ensure evidence records are saved per repository snapshot without cross-tenant collisions.
   - **Test:** `tests/security/test_hidden_multitenant_evidence.py`

3. **CT-HIDDEN-03: FindingFeedbackCreate Schema Normalization**
   - **File:** `packages/schemas/changetrace_schemas/models.py`
   - **Change:** In `FindingFeedbackCreate`, accept `"ACCEPTED"`, `"CONFIRM"`, `"REJECT"`, `"REJECTED"`, `"NOT_RELEVANT"`.
   - **Test:** `tests/security/test_feedback_decision.py`

4. **CT-HIDDEN-04: Row-Level Security for Remaining Tables**
   - **File:** `infrastructure/migrations/versions/004_row_level_security.sql` and `005_github_tenant_and_deliveries.sql`
   - **Change:** Add RLS policies and `FORCE ROW LEVEL SECURITY` to `users`, `github_installations`, `github_webhook_deliveries`.
   - **Test:** `tests/integration/test_postgres_migrations_and_rls.py`

5. **CT-HIDDEN-05: Algorithmic Memory Exhaustion on `/api/v1/risks/{risk_id}`**
   - **File:** `apps/api/changetrace_api/main.py`
   - **Change:** Bound the query for `AnalysisRun` to the most recent 20 runs, preventing O(N) memory exhaustion.
   - **Test:** `tests/security/test_hidden_risk_query.py`

6. **CT-HIDDEN-06: Rate Limiter Proxy IP Trust Boundary**
   - **File:** `apps/api/changetrace_api/main.py`
   - **Change:** In `secure_and_trace`, only trust `X-Forwarded-For` if `request.client.host` is a verified local trusted proxy (`127.0.0.1`, `::1`, `localhost`). Otherwise use `request.client.host`.
   - **Test:** `tests/security/test_rate_limiter_hardening.py`

7. **CT-HIDDEN-07: Restrict Default Seeding in Production Lifespan**
   - **File:** `apps/api/changetrace_api/main.py`
   - **Change:** Only seed `dev@changetrace.local` and default organization if `settings.environment != "production"` and `settings.auth_mode == "development"`.
   - **Test:** `tests/security/test_hidden_lifespan_hardening.py`

8. **CT-HIDDEN-08: Git Argument Injection in Ref Comparison**
   - **File:** `services/repository_analysis/diff.py`
   - **Change:** Reject refs starting with `-` (`ref.startswith("-")`) and pass `--end-of-options` to git commands.
   - **Test:** `tests/security/test_hidden_git_ref_injection.py`

9. **CT-HIDDEN-09: Production Session Secret Validation**
   - **File:** `apps/api/changetrace_api/config.py`
   - **Change:** Add validator in `Settings` to reject `session_secret == "change-me-in-production"` when `environment == "production"`.
   - **Test:** `tests/security/test_hidden_config_hardening.py`
