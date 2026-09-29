# Segregate Codebase into Backend and Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the ChangeTrace monorepo into clean, segregated top-level `backend/` and `frontend/` directories while maintaining 100% test pass rate, full Docker container compatibility, and zero broken imports.

**Architecture:** 
- `frontend/` will contain the React/TypeScript/Vite web application migrated from `apps/web/`, complete with its own package configuration and static Nginx Dockerfile.
- `backend/` will contain all Python backend services, API modules, analysis engines, worker queues, schemas, database migrations, and test suites.
- Root configuration files (`docker-compose.yml`, root `pyproject.toml`) will be updated to point directly to `backend/` and `frontend/` workspaces, allowing seamless test execution and multi-container orchestration.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL (pgvector), Redis/RQ, Vite, React, TypeScript, Docker.

---

### File Relocation Mapping

| Original Path | Target Path | Purpose |
| :--- | :--- | :--- |
| `apps/web/` | `frontend/` | React/Vite SPA |
| `apps/api/` | `backend/apps/api/` | FastAPI routes, models, and auth |
| `services/` | `backend/services/` | Core analysis, verification & GitHub engines |
| `workers/` | `backend/workers/` | Background RQ job pipeline |
| `packages/` | `backend/packages/` | Shared Pydantic schemas |
| `infrastructure/` | `backend/infrastructure/` | Database migrations and API Dockerfile |
| `tests/` | `backend/tests/` | Unit, integration, security & benchmark tests |
| `pyproject.toml` | `backend/pyproject.toml` | Backend packaging and dependencies |

---

### Tasks

#### Task 1: Migrate Frontend to `frontend/`
- [ ] Move `apps/web` directory to `frontend/`.
- [ ] Copy `infrastructure/docker/nginx.conf` into `frontend/nginx.conf`.
- [ ] Create `frontend/Dockerfile` targeting the new path (`COPY package*.json ./`, `COPY . ./`, Nginx runtime).
- [ ] Verify `npm test` or build check passes inside `frontend/`.

#### Task 2: Migrate Backend Modules into `backend/`
- [ ] Create `backend/` directory.
- [ ] Move `apps/api` to `backend/apps/api`.
- [ ] Move `services/` to `backend/services/`.
- [ ] Move `workers/` to `backend/workers/`.
- [ ] Move `packages/` to `backend/packages/`.
- [ ] Move `infrastructure/` to `backend/infrastructure/`.
- [ ] Move `tests/` to `backend/tests/`.
- [ ] Remove empty `apps/` directory.

#### Task 3: Configure Backend Packaging & Python Environment
- [ ] Create `backend/pyproject.toml` with paths relative to `backend/`.
- [ ] Update root `pyproject.toml` to configure `pytest` pythonpath targeting `["backend", "backend/apps/api", "backend/packages/schemas"]` and `testpaths = ["backend/tests"]`.
- [ ] Create `backend/infrastructure/docker/api.Dockerfile` updated for the `backend/` build context.

#### Task 4: Update Container Orchestration & Environment Files
- [ ] Update `docker-compose.yml`:
  - Update `postgres` init volume to `./backend/infrastructure/migrations/versions:/docker-entrypoint-initdb.d:ro`.
  - Update `api` build context to `./backend` with `dockerfile: infrastructure/docker/api.Dockerfile`.
  - Update `worker` build context to `./backend` with `dockerfile: infrastructure/docker/api.Dockerfile`.
  - Update `web` build context to `./frontend` with `dockerfile: Dockerfile`.
- [ ] Update `docker-compose.prod.yml` with the same updated paths.
- [ ] Update `.env` and `.env.example` paths if needed.

#### Task 5: Comprehensive Verification & Test Suite Execution
- [ ] Run `python -m pytest` from the root directory to verify all 170+ tests pass with zero path errors.
- [ ] Run unit and security tests specifically (`python -m pytest backend/tests/security`, `backend/tests/unit`).
- [ ] Verify Docker build commands (`docker build -t changetrace-api -f backend/infrastructure/docker/api.Dockerfile backend`).
