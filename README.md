# ChangeTrace

> **Know what your change will break before you make it.**

ChangeTrace is an evidence-first **Git-Native Change Impact & State-Machine Simulator**. It connects a natural-language requirement and optional proposed Git diff directly to affected code, cross-language state machines, database models, API contracts, deterministic risks, verified test gaps, and a fail-closed GO / REVIEW / BLOCK decision for Pull Requests.

### Strategic Scope Boundaries

- **In-Scope (Kept & Hardened):** Git repository intelligence, unified diffs, AST parsing (Python, TS/JS, SQL via Tree-sitter), in-memory directed dependency graphs (NetworkX), immutable SHA-256 evidence verification, deterministic 95-point risk engine, cross-service contradiction detection, test-gap derivation, and automated GitHub Check Runs / PR comments.
- **Explicitly Out-of-Scope (Killed):** No CRM (Salesforce) or ERP (SAP/NetSuite) connectors; no Jira ticket or Confluence wiki crawling; no spreadsheet/CSV business rule pipelines; no runtime log/telemetry ingestion; no universal enterprise CMDB; no "multi-agent" marketing hype; no hardcoded business-rule heuristics; no fake/demo numbers; and no generic AI-generated change plans.

## Implemented workflow

```text
repository snapshot + proposed requirement + optional diff/refs
→ before/after source indexes and graph delta
→ impact + state-machine/rule discovery
→ immutable evidence + evidence strength
→ deterministic risk + independent confidence
→ focused test gaps + adversarial support status
→ fail-closed verification
→ actionable plan + GO/REVIEW/BLOCK
```

Python and TypeScript/JavaScript use deep Tree-sitter extraction (routes, calls, side-effects, state assignments) with resilient fallback. Incremental index reuse invalidates cross-file relationships and persists caches to disk. PostgreSQL stores tenant-scoped snapshots/results/evidence/feedback; Redis/RQ handles Compose jobs. The GitHub App service manages authenticated webhook ingestion, multi-tenant resolution, delivery deduplication, and automated check runs / PR comments. The OpenAI-compatible abstraction is isolated and optional—the current pipeline remains deterministic and reports semantic analysis as degraded without a configured model.

## Run locally

```bash
python -m pip install -e ".[dev]"
cd apps/web && npm install && cd ../..
# PowerShell: $env:CHANGETRACE_LOCAL_REPOSITORY_ROOT=(Get-Location).Path
uvicorn changetrace_api.main:app --app-dir apps/api --reload
# second terminal
cd apps/web && npm run dev
```

Open `http://localhost:5173`, select `tests/evaluation/demo_repository`, sync it, optionally paste a unified Git diff, and simulate.

## Quality commands

```bash
make lint
make typecheck
make test
make benchmark
make build
make e2e
```

The expanded benchmark has 33 labeled synthetic scenarios. The latest measured fixture-only results are in [`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md).

## Evidence and decisions

Evidence includes repository/snapshot/commit identity, file/lines/symbol, reason, strength (`DIRECT`, `STRONG`, `INDIRECT`, `SEMANTIC`, `INFERRED`, `UNCERTAIN`), quality score, and SHA-256. Verification recomputes source hashes and rejects nonexistent/cross-snapshot references.

Risk uses the documented 95-point baseline—dependency impact 25, criticality 25, test gaps 20, integration exposure 15, ambiguity 10—with bounded explicit uplifts for change distance, boundary spread, and state transitions. Models cannot choose numeric scores. Decision policy blocks only when supported high-confidence critical risk and critical missing verification coincide; otherwise verified risk/gaps/contradictions require review.

## Docker runtime

Compose defines PostgreSQL/pgvector, Redis, API, RQ worker, and web. Configure a non-default `POSTGRES_PASSWORD` in the environment, then run:

```bash
docker compose config
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

Apply the ordered SQL files in `infrastructure/migrations/versions/` using the transactional migration runner (`infrastructure/migrations/runner.py`) before production startup. If the Docker daemon is unavailable, configuration can still be validated, but database, Redis, worker, API, and web runtime checks remain environment-blocked. See [`docs/DOCKER_VERIFICATION.md`](docs/DOCKER_VERIFICATION.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Diff simulation](docs/DIFF_SIMULATION.md)
- [Business rules](docs/BUSINESS_RULES.md)
- [Data model](docs/DATA_MODEL.md)
- [API](docs/API_SPEC.md)
- [Engine contracts](docs/AGENT_CONTRACTS.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Evaluation plan](docs/EVALUATION_PLAN.md) and [results](docs/EVALUATION_RESULTS.md)
- [Implementation assessment](docs/NEXT_IMPLEMENTATION_ASSESSMENT.md)
- [Demo](docs/DEMO_SCRIPT.md)
- [Roadmap](ROADMAP.md)

## Current limitations

- Evaluation uses synthetic repositories and does not establish production accuracy; subscription evidence precision remains below the desired target.
- The 33 scenarios share one synthetic repository and are not a held-out production benchmark.
- Docker runtime execution and live pgvector container initialization remain environment-blocked on this host due to the Docker Desktop daemon being unavailable (Compose configuration, Dockerfiles, and migration scripts are validated).
