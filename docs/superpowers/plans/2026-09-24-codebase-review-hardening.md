# ChangeTrace Codebase Review Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Inline execution with verification checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address all 12 items identified in the codebase review: add missing PyJWT crypto dependency, implement secure GitHub webhook multi-tenant resolution and deduplication, connect analysis completion to GitHub Check Runs and PR comments, harden GitHub App token lifecycle, deepen Tree-sitter extraction (routes, calls, imports, TypeScript state machines, side-effects, SQL), harden incremental graph rebuilding, optimize impact/evidence precision, expand state-machine and contradiction analysis, add frontend unit/component tests in Vitest, unify database migration execution, and update documentation.

**Architecture:** 
1. Dependencies & Security: Add `PyJWT[crypto]` to `pyproject.toml`.
2. Multi-tenant GitHub: Database migration `005_github_tenant_and_deliveries.sql` creates `github_installations` (linking `installation_id` to `organization_id`) and `github_webhook_deliveries` (deduplication & replay protection).
3. Pipeline Hook: In `workers/analysis/pipeline.py` & API routes, trigger `GitHubChecksService.create_or_update_check_run()` and `post_pr_comment()` upon analysis completion.
4. Token Lifecycle: Robust `expires_at` parsing, PEM normalization, strict development-only mock gating, retry backoff in `services/github/app.py`.
5. Deep Tree-sitter & Incremental: Route, call, import, SQL, and side-effect extraction in `services/repository_analysis/treesitter_parser.py`; graph edge invalidation and cross-file invariant verification in `services/repository_analysis/incremental.py`.
6. Precision & State Machines: Causal path ranking, dead-code reachability, diff symbol seeding in `services/impact/engine.py`; TypeScript state-machine & multi-step contradiction modeling.
7. Frontend Testing: Unit and component tests in `apps/web/src/__tests__/` with Vitest, removing `--passWithNoTests`.
8. Documentation: Reflect accurate implementation and environment status in `README.md` and `ROADMAP.md`.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, PostgreSQL, Redis, RQ, NetworkX, Tree-sitter, Vitest, React 19, TypeScript.

---

### Task 1: Dependency & Environment Configuration
- [ ] Add `"PyJWT[crypto]>=2.9,<3"` to `pyproject.toml`.
- [ ] Verify PyJWT with cryptographic key parsing.

### Task 2: GitHub Webhook Multi-Tenant Resolution & Delivery Deduplication
- [ ] Add `005_github_tenant_and_deliveries.sql` migration for `github_installations` and `github_webhook_deliveries`.
- [ ] Add SQLAlchemy models `GitHubInstallationModel` and `GitHubWebhookDeliveryModel` in `apps/api/changetrace_api/models.py`.
- [ ] Update `services/github/webhooks.py` to persist/lookup installation mapping, reject unmapped tenants, and enforce delivery ID deduplication.
- [ ] Write unit and integration tests verifying tenant isolation, installation routing, and replay rejection.

### Task 3: GitHub App Token Lifecycle Hardening
- [ ] In `services/github/app.py`, parse GitHub `expires_at` timestamp with safety buffer.
- [ ] Add RSA private key normalization (support raw PEM, newline-escaped PEM, or file path).
- [ ] Strictly restrict mock tokens to explicit dev/test environments.
- [ ] Add API rate-limit/retry handling.
- [ ] Write unit tests verifying token lifecycle and error handling.

### Task 4: Connect Analysis Completion to GitHub Checks & PR Comments
- [ ] In `workers/analysis/pipeline.py` and `apps/api/changetrace_api/main.py`, trigger GitHub Check Run updates and PR comment posting on analysis completion when GitHub metadata is present.
- [ ] Write test verifying completed analysis triggers check run and PR comment posting.

### Task 5: Deepen Tree-sitter AST & Syntax Extraction
- [ ] Expand `TreeSitterParser` in `services/repository_analysis/treesitter_parser.py`:
  - Route extraction (FastAPI/Flask decorators, Express/Next.js routes).
  - Call and import extraction.
  - TypeScript state machine declarations & side-effects.
  - SQL semantic extraction.
  - Metrics tracking (`TreeSitterMetrics`).
- [ ] Write comprehensive unit tests in `tests/unit/test_treesitter_deep.py`.

### Task 6: Incremental Graph Rebuilding & Cross-File Integrity
- [ ] In `services/repository_analysis/incremental.py`:
  - Invalidate cross-file edges pointing to modified/deleted symbols.
  - Purge dangling relationships from deleted files.
  - Add index cache persistence interface across runs.
- [ ] Write unit tests verifying graph edge invalidation.

### Task 7: Impact Precision Optimization & Precision Tuning
- [ ] In `services/impact/engine.py` and `services/graph/repository_graph.py`:
  - Add causal path ranking prioritizing paths seeded by changed diff ranges.
  - Prune dead code and unrelated modules.
  - Refine risk scoring based on blast radius rather than raw component counts.
- [ ] Validate benchmark suites.

### Task 8: State-Machine & Multi-Step Contradiction Analysis
- [ ] Expand `services/state_machines/engine.py` and `services/business_rules/contradictions.py` for conditional business rules and multi-step transitions.
- [ ] Write unit tests validating complex contradiction patterns.

### Task 9: Frontend Unit & Component Tests
- [ ] Configure Vitest with jsdom in `apps/web/vite.config.ts`.
- [ ] Write unit and component tests in `apps/web/src/__tests__/`:
  - `api.test.ts`
  - `PrecisionDashboard.test.tsx`
  - `App.test.tsx`
- [ ] Update `package.json` to run `vitest run` without `--passWithNoTests`.
- [ ] Verify `npm run test` passes cleanly.

### Task 10: Unified Migration Runner & Locking
- [ ] Enhance `infrastructure/migrations/runner.py` with migration locking and history tracking.
- [ ] Test migration runner against `005_github_tenant_and_deliveries.sql`.

### Task 11: Documentation Updates
- [ ] Update `README.md` and `ROADMAP.md` to accurately reflect all implemented, integrated, tested, and environment-blocked features.
