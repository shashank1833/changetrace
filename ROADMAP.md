# Roadmap

## Completed Milestones

### Core Analysis & Deep Extraction
- **Tree-sitter Integration:** Multi-language extraction for Python, TypeScript/JavaScript, and SQL. Extracts route definitions (FastAPI & Express), call/import hierarchies, database mutations, HTTP calls, and state assignments with resilient fallback.
- **Cross-Language State Machines:** State and transition extraction across Python enums and TypeScript types/unions, mapped to side-effects and test assertions.
- **Advanced Contradiction Detection:** Behavioral opposition detection across documentation vs code, conflicting code guards across services, and test expectations vs unguarded implementations.
- **Incremental Index Reuse:** Cache invalidation for modified and deleted files, cross-file edge rebuilding, and persistent disk cache (`save_cache`/`load_cache`) with full fallback.

### Precision & Risk Modeling
- **Directed Path Ranking:** Causal reachability traversal with dead-code exclusion and boundary-aware candidate filtering.
- **Diff-Aware Simulation:** Unified Git diff parsing, changed symbol seeding, and before/after graph delta analysis.
- **Feedback & Calibration:** Human-in-the-loop finding feedback, explainable precision calibration dashboards, and strict isolation preventing automatic model retraining.

### GitHub Integration & Production Lifecycle
- **GitHub App & Token Lifecycle:** Installation token minting with JWTs, normalized PEM private key parsing, Redis-coordinated caching, and mock rejection in production.
- **Signed Webhooks & Multi-Tenancy:** `X-Hub-Signature-256` HMAC verification, multi-tenant installation-to-organization mapping, and `X-GitHub-Delivery` replay deduplication.
- **Checks & PR Comments:** Automatic `create_or_update_check_run` and `post_pr_comment` execution upon analysis completion.
- **Database Migrations:** Transactional migration runner with advisory locks (`schema_migration_locks`) and Docker startup integration.
- **Frontend Quality:** Vitest unit and component test suite covering API client, `PrecisionDashboard`, `EvidenceDrawer`, and main application.

## Environment-Blocked

- **P0.1 Docker Runtime Verification:** Configuration and Dockerfiles validated; container spin-up blocked on Windows host due to unavailable Docker Desktop daemon service access.

## Explicitly Rejected / Killed Out-of-Scope Items

To prevent scope creep and maintain a laser-focused, defensible product, the following items are **explicitly killed**:
- **CRM / ERP Connectors:** Salesforce, SAP, NetSuite, and generic business systems rejected as an enterprise integration tarpit.
- **Jira & Confluence Scraping:** Dropped in favor of Git-native pull request descriptions and in-repo committed documentation.
- **Spreadsheets / CSV Rules:** Out of scope; business rules must be expressed in code or repo-tracked specifications.
- **Runtime Log & APM Ingestion:** Dropped; ChangeTrace is a pre-merge, pre-change impact simulator, not a runtime observability suite.
- **Universal Enterprise CMDB:** Dropped in favor of high-precision per-repository AST graphs and Git diff deltas.
- **"Multi-Agent" Marketing:** Rejected; replaced with transparent, deterministic, schema-constrained analysis engines.
- **Hardcoded Heuristics:** Eliminated in favor of structural state-machine tracking and evidence reachability.
- **Generic AI Change Plans:** Replaced with concrete, component-anchored implementation steps.

## Next Priorities

1. Expand Tree-sitter grammars to additional target languages (Go, Java, Rust).
2. Deepen SQL DDL migration parsing (detecting breaking column/type drops against existing query references).
3. Continuous evaluation against held-out customer repositories beyond synthetic benchmarks.
4. Production sandbox isolation limits and self-hosted GitHub App distribution.

