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

## Next Priorities

1. Expand Tree-sitter grammars to additional target languages (Go, Java, Rust).
2. Continuous evaluation against held-out customer repositories beyond the 33 synthetic benchmark scenarios.
3. OpenTelemetry distributed tracing exporter and production sandbox isolation limits.

