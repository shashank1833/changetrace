# ChangeTrace

<p align="center">
  <strong>Know what your change will break before you make it.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19.0-61DAFB?logo=react&logoColor=black" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Tests-170%20passed-brightgreen?logo=pytest&logoColor=white" alt="Tests" />
  <img src="https://img.shields.io/badge/Security-Hardened%20(RLS)-success" alt="Security Hardened" />
</p>

---

## Overview

**ChangeTrace** is an evidence-first **Git-Native Change Impact & State-Machine Simulator**. It connects a natural-language change request and proposed Git diff directly to:

- **Affected Code & Downstream Dependents:** Deterministic call-graph and import-graph traversal across files, components, and libraries.
- **Cross-Language State Machines:** Automated discovery and invariant tracking across Python, TypeScript/JavaScript, and SQL schemas.
- **Contract & API Exposure:** Verification of modified HTTP route contracts, database entities, and background worker jobs.
- **Contradiction Detection:** Automatic flagging of conflicts between documentation rules, test assertions, and code implementations.
- **Missing Verification Test Gaps:** Identification of untested critical behaviors and regression risk scenarios.
- **Fail-Closed Release Decisions:** Automated **`GO`**, **`REVIEW`**, or **`BLOCK`** check runs and comments on GitHub Pull Requests.

---

## Repository Architecture

The codebase is organized into segregated `backend/` and `frontend/` workspaces:

```
changetrace/
├── backend/                             # Python Backend Engine & Services
│   ├── apps/
│   │   └── api/                         # FastAPI REST & WebSocket server
│   │       └── changetrace_api/         # Routes, Auth, RBAC, Models, Telemetry
│   ├── services/                        # Domain & Analysis Engines
│   │   ├── business_rules/              # Contradiction detection
│   │   ├── changes/                     # Change intent interpretation
│   │   ├── decisions/                   # 95-point risk policy decision engine
│   │   ├── evidence/                    # Immutable evidence hash collection
│   │   ├── feedback/                    # Dynamic model calibration
│   │   ├── github/                      # Check runs, comments, and webhook processor
│   │   ├── graph/                       # NetworkX repository dependency graph
│   │   ├── impact/                      # Multi-hop impact analysis engine
│   │   ├── repository_analysis/         # Tree-sitter & AST parsers, diff engine
│   │   ├── retention/                   # Safe tenant data pruning & secret redaction
│   │   ├── risks/                       # Deterministic risk & factor scoring
│   │   ├── state_machines/              # State transition discovery & validations
│   │   └── test_gaps/                   # Test scenario & regression coverage engine
│   ├── workers/                         # Background asynchronous RQ worker pipelines
│   ├── packages/                        # Shared Pydantic schemas (changetrace_schemas)
│   ├── infrastructure/                  # PostgreSQL RLS migrations & container specs
│   ├── tests/                           # Unit, integration, security & benchmark tests
│   └── pyproject.toml                   # Backend dependencies & tool configurations
│
├── frontend/                            # React + TypeScript Web Application
│   ├── src/                             # React 19 application source code
│   │   ├── components/                  # Impact graph (React Flow), evidence drawer, dashboard
│   │   ├── lib/                         # API client & WebSocket streaming
│   │   ├── styles.css                   # Responsive layout & theme styles
│   │   └── App.tsx                      # Main application UI
│   ├── Dockerfile                       # Multi-stage production container build (Vite + Nginx)
│   ├── nginx.conf                       # Production Nginx reverse-proxy & security headers
│   ├── package.json                     # Frontend scripts & dependencies
│   └── vite.config.ts                   # Vite bundler configuration
│
├── docker-compose.yml                   # Local containerized development orchestration
├── docker-compose.prod.yml              # Production container orchestration
├── pyproject.toml                       # Root project metadata & test discovery
├── .env.example                         # Environment configuration template
└── README.md
```

---

## Key Capabilities

### 1. Deterministic Multi-Layer Analysis
- **Deep Tree-sitter AST Extraction:** Parses Python, TypeScript, JavaScript, and SQL into structured symbols, routes, state mutations, and calls with fallback parsers.
- **Immutable SHA-256 Evidence Records:** Every risk claim, test gap, and rule is cryptographically tied to exact source-code spans and snapshot commit hashes.
- **Fail-Closed Decision Engine:** Evaluates release confidence using strict mathematical policies—no probabilistic LLM makes release-blocking decisions without verified evidence.

### 2. Multi-Tenant Enterprise Security
- **PostgreSQL Row-Level Security (RLS):** All 12 tables (`repositories`, `snapshots`, `evidence`, `artifacts`, `users`, `audit_logs`, etc.) enforce database-level tenant isolation using `FORCE ROW LEVEL SECURITY`.
- **Role-Based Access Control (RBAC):** Strict permissions model (`OWNER`, `ADMIN`, `MEMBER`, `VIEWER`) protecting destructive endpoints, session pruning, and audits.
- **Adversarial Hardening:** Protection against path traversal, command flag injection, SSRF, cloud metadata access, and webhook replay attacks.
- **Automated Secret Redaction:** Regex-based scrubbing of AWS, OpenAI (`sk-proj-`), Slack (`xoxb-`), Anthropic, and RSA private keys before storage.

---

## Quickstart: Running Locally

### Option A: Docker Compose (Recommended)

Run all services (PostgreSQL + pgvector, Redis, FastAPI backend, RQ worker, and React frontend) with a single command:

```bash
# 1. Clone the repository
git clone https://github.com/shashank1833/changetrace-.git
cd changetrace-

# 2. Copy the environment configuration
cp .env.example .env

# 3. Start all containers
docker compose up -d --build
```

- **Web UI:** [http://localhost:5173](http://localhost:5173)
- **API Server:** [http://localhost:8000](http://localhost:8000)
- **API Health:** [http://localhost:8000/health](http://localhost:8000/health)

---

### Option B: Local Development Setup

#### 1. Backend Setup (Python 3.12+)
```bash
# Install backend in editable mode with development dependencies
python -m pip install -e ".[dev]"

# Start the API server
uvicorn backend.apps.api.changetrace_api.main:app --reload --port 8000
```

#### 2. Frontend Setup (Node 20+)
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Testing & Quality Assurance

ChangeTrace maintains automated test coverage across unit logic, live integration flows, evaluations, and security loophole penetration:

```bash
# Run the complete test suite (170+ tests)
python -m pytest

# Run security test suites specifically
python -m pytest backend/tests/security

# Run integration tests
python -m pytest backend/tests/integration

# Run frontend tests
cd frontend && npm test
```

### Test Suite Breakdown:
- **Security Tests:** 41 / 41 passing (Multi-tenant RLS, auth hardening, path traversal, SSRF prevention)
- **Unit Tests:** 112 / 112 passing (Impact precision, test gaps, state machines, AST parsing)
- **Evaluation Benchmark:** 5 / 5 passing (Deterministic accuracy on evaluation repositories)
- **Integration Tests:** 12 passing (Database migration runner, API contracts, Redis RQ queue)

---

## Production Deployment

### 1. Environment Configuration
Create `.env.production` with secure credentials:

```ini
CHANGETRACE_ENVIRONMENT=production
CHANGETRACE_AUTH_MODE=oauth
CHANGETRACE_SESSION_COOKIE_SECURE=true
CHANGETRACE_SESSION_SECRET=<64-char-random-hex>
CHANGETRACE_ALLOWED_ORIGINS=https://changetrace.yourdomain.com
CHANGETRACE_WEB_URL=https://changetrace.yourdomain.com
CHANGETRACE_GITHUB_CLIENT_ID=<your-github-client-id>
CHANGETRACE_GITHUB_CLIENT_SECRET=<your-github-client-secret>
CHANGETRACE_GITHUB_CALLBACK_URL=https://changetrace.yourdomain.com/api/v1/auth/github/callback
POSTGRES_PASSWORD=<strong-postgres-password>
CHANGETRACE_REDIS_PASSWORD=<strong-redis-password>
```

### 2. Launch with Production Compose
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

### 3. Free Domain & SSL Options (If you don't own a custom domain)
- **Public VPS (AWS, DigitalOcean, Hetzner):** Use **`sslip.io`** (e.g., `https://<your-ip>.sslip.io`) with Let's Encrypt Certbot.
- **Local / Home Server:** Use **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:8080`) for instant free HTTPS.
- **Local Testing:** GitHub OAuth officially supports `http://localhost:8080` without requiring any domain.

---

## License

This project is licensed under the Apache 2.0 License.
