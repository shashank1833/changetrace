# Data Model

Tenant ownership follows Organization → Repository → Snapshot/Change → Analysis.

| Entity | Important fields / constraints |
|---|---|
| repositories | organization FK, confined local path or GitHub URL |
| repository_snapshots | repository FK, immutable commit/content SHA, analyzer version/status |
| change_requests | repository/org FKs, description, optional proposed diff or base/target refs |
| analysis_jobs | durable state/progress/error |
| analysis_runs | snapshot, commit, analyzer/model versions, validated result JSON |
| evidence | snapshot, repository/commit in payload, source location, strength, quality, SHA-256 |
| analysis_artifacts | typed envelope for symbols/dependencies/intent/rules/impact/risk/test gaps |
| finding_feedback | analysis/finding/user, CONFIRM/REJECT/NOT_RELEVANT, reason, analyzer version, timestamp |
| audit_logs | tenant/actor/action/resource; no source content |

`AnalysisResult` now includes optional `ChangeSet`, `GraphDelta`, discovered state machines, paired-evidence contradictions, evidence quality, and an explicit decision.

Migration `001_initial.sql` establishes core tables and pgvector; `002_diff_feedback.sql` adds diff inputs and finding feedback. Local SQLite uses a narrow compatibility migration because `create_all` cannot alter existing contributor databases. Production must apply versioned SQL migrations.
