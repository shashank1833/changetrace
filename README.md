# ChangeTrace

> **Know what your change will break before you make it.**

ChangeTrace is an evidence-first **Business Change Simulator**. It connects a natural-language requirement and optional proposed Git diff to affected code, business rules, states, data paths, integrations, tests, deterministic risks, and a GO / REVIEW / BLOCK recommendation.

It is not a generic code reviewer, chatbot, CMDB, observability suite, or autonomous coding agent.

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

Python uses AST analysis; TypeScript/JavaScript/SQL use conservative baseline extraction. NetworkX performs bounded traversal. PostgreSQL stores tenant-scoped snapshots/results/evidence/feedback; Redis/RQ handles Compose jobs. The OpenAI-compatible abstraction is isolated and optional—the current pipeline remains deterministic and reports semantic analysis as degraded without a configured model.

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

The expanded benchmark has 33 labeled synthetic scenarios. The latest measured fixture-only results are in [`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md). They show high recall but low precision; they are not general accuracy claims.

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

Apply the ordered SQL files in `infrastructure/migrations/versions/` to an isolated PostgreSQL database before production-style startup. If the Docker daemon is unavailable, configuration can still be validated, but database, Redis, worker, API, and web runtime checks remain environment-blocked. See [`docs/DOCKER_VERIFICATION.md`](docs/DOCKER_VERIFICATION.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Diff simulation](docs/DIFF_SIMULATION.md)
- [Business rules](docs/BUSINESS_RULES.md)
- [Data model](docs/DATA_MODEL.md)
- [API](docs/API_SPEC.md)
- [Agent contracts](docs/AGENT_CONTRACTS.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Evaluation plan](docs/EVALUATION_PLAN.md) and [results](docs/EVALUATION_RESULTS.md)
- [Implementation assessment](docs/NEXT_IMPLEMENTATION_ASSESSMENT.md)
- [Demo](docs/DEMO_SCRIPT.md)
- [Roadmap](ROADMAP.md)

## Current limitations

- Evaluation uses synthetic repositories and does not establish production accuracy; subscription evidence precision remains below the desired target.
- The 33 scenarios share one synthetic repository and are not a held-out production benchmark.
- Tree-sitter is not yet integrated; TS/JS extraction is pattern based.
- Incremental index reuse and GitHub PR webhooks/checks are not implemented.
- GitHub App token lifecycle and production authentication are not implemented.
- State-machine extraction recognizes Python enums and literal transition maps; side-effect mapping is incomplete.
- Contradiction detection is conservative and lexical.
- Docker runtime and pgvector extension initialization remain unverified on this host.
