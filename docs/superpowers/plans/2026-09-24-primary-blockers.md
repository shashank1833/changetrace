# Primary Blockers Implementation Plan

## Goal
Resolve the 7 primary blockers identified in the codebase review:
1. Fix PostgreSQL execution of `DO $$` migrations in `runner.py`.
2. Add runtime RLS tenant context (`app.current_organization_id`) in sessions/queries.
3. Make GitHub webhook delivery deduplication atomic using database constraints.
4. Enforce mandatory webhook signature verification.
5. Document Docker Desktop daemon environment constraints and elevated verification steps.
6. Improve evidence and test-gap precision toward documented targets.
7. Update evaluation documentation (`docs/EVALUATION_RESULTS.md`) with current benchmark measurements.

---

### Phase 1: Fix PostgreSQL Execution of `DO $$` Migrations
- **File**: `infrastructure/migrations/runner.py`
- **Action**: Implement `split_sql_statements(sql: str) -> list[str]` supporting dollar quotes, single quotes, and SQL comments.
- **Verification**: `tests/unit/test_migration_runner.py`

### Phase 2: Runtime RLS Tenant Context
- **Files**:
  - `apps/api/changetrace_api/database.py` (add `set_tenant_context`)
  - `apps/api/changetrace_api/main.py` (wire into sessions and analysis jobs)
  - `services/github/webhooks.py` (wire into webhook tenant processing)
- **Verification**: `tests/unit/test_tenant_authorization.py`

### Phase 3: Atomic Webhook Deduplication
- **File**: `services/github/webhooks.py`
- **Action**: Implement `_claim_delivery` using atomic insert with `IntegrityError` duplicate detection.
- **Verification**: `tests/unit/test_github_integration.py`

### Phase 4: Mandatory Webhook Signature Verification
- **File**: `apps/api/changetrace_api/main.py`
- **Action**: Require secret in production; require `x-hub-signature-256` and verify HMAC when configured.
- **Verification**: `tests/unit/test_github_integration.py`

### Phase 5: Docker Runtime Status & Diagnostics
- **File**: `docs/DOCKER_VERIFICATION.md`, `README.md`, `ROADMAP.md`
- **Action**: Record exact PowerShell service status (`Stopped`), unprivileged error, and administrative reproduction instructions.

### Phase 6: Evidence & Test-Gap Precision Tuning
- **Files**:
  - `workers/analysis/pipeline.py` / `services/evidence/engine.py` (filter/rank evidence to primary intent-aligned components)
  - `services/test_gaps/engine.py` (tighten category triggers against explicit intent words)
- **Verification**: `python tests/evaluation/benchmark/run.py`

### Phase 7: Evaluation Documentation Refresh
- **File**: `docs/EVALUATION_RESULTS.md`
- **Action**: Update with current measured results across all benchmarks and compare with quality targets.

### Phase 8: Full Suite Verification
- `pytest tests/ -v`
- `npm --prefix apps/web test -- --run`
- `npm --prefix apps/web run build`
- `ruff check .`
- `mypy apps/api services/ packages/ infrastructure/ tests/`
- `python tests/evaluation/benchmark/run.py`
- `python tests/evaluation/cross_domain/run.py`
- `python tests/evaluation/held_out/run.py`
