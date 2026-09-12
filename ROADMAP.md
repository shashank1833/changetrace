# Roadmap

## Completed vertical slice

Repository snapshots, Python AST plus baseline TS/JS/SQL indexing, graph traversal, structured intent, immutable evidence, deterministic risk/confidence, adversarial status, test gaps, verification, API/UI, PostgreSQL/Redis definitions, Docker/CI, and the original controlled demo.

## Current milestone — business change simulation

- **P0.1 Docker runtime verification:** blocked by unavailable Docker Desktop daemon; configuration validated and exact rerun documented.
- **P0.2 expanded benchmark:** 33 machine-readable scenarios and measured baseline implemented. Precision is currently low and remains the principal quality target.
- **P0.3 diff-aware simulation:** proposed unified diff and local branch/commit comparison, before/after indexes, graph delta, changed-component impact seeding, API persistence, and UI input implemented.
- **P1.1 state-machine reasoning:** Python enum states and literal transition maps implemented at baseline depth.
- **P1.2 contradiction detection:** conservative documentation/code paired-evidence detector implemented.
- **P1.3 evidence quality:** strength and quality score implemented and shown in UI.

## Next, in order

1. Improve impact/evidence precision using directed path ranking, dead-code reachability, and boundary-aware candidate thresholds; re-run the held-out benchmark.
2. Expand transition side-effect and transition-test mapping, including TypeScript Tree-sitter queries.
3. Add safe incremental index reuse with full-analysis fallback and measured timings.
4. Expand finding feedback reporting and precision dashboards. Feedback must not retrain models automatically.
5. Add GitHub App authentication, signed webhooks, PR diff ingestion, checks, and concise comments only after core precision is acceptable.
6. Add production migration runner, PostgreSQL RLS, distributed rate limits, OTel exporter, sandbox limits, and container runtime verification.

Language expansion remains gated on measured core quality.
