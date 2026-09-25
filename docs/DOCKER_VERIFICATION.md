# Docker Runtime Verification

## Environment & Diagnostic Audit

- Date: 2026-09-24
- Host: Windows, Docker context `desktop-linux`
- Docker CLI: 29.6.2
- Docker Compose: v5.3.1
- Shell: PowerShell (unprivileged agent environment)

## Commands and Diagnostic Results

### 1. Engine Connectivity
`docker info` returned:

```text
Client:
 Version:    29.6.2
 Context:    desktop-linux
 Plugins: buildx, compose, scout, etc.
Server:
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine:
The system cannot find the file specified.
```

### 2. Windows Service Inspection
`Get-Service *docker*` returned:

```text
Status   Name               DisplayName
------   ----               -----------
Stopped  com.docker.service Docker Desktop Service
```

### 3. Service Start Attempt
`Start-Service com.docker.service` returned:

```text
Start-Service : Service 'Docker Desktop Service (com.docker.service)' cannot be started due to:
Cannot open com.docker.service service on computer '.'.
At line:1 char:1
+ Start-Service com.docker.service
    + CategoryInfo          : OpenError: (System.ServiceProcess.ServiceController:ServiceController) [Start-Service], ServiceCommandException
    + FullyQualifiedErrorId : CouldNotStartService,Microsoft.PowerShell.Commands.StartServiceCommand
```

*Diagnosis:* Docker Desktop's underlying service `com.docker.service` is stopped, and starting Windows system services requires elevated Administrator (UAC) permissions that are unavailable in this unprivileged agent session.

### 4. Static Configuration Validation
`docker compose config` succeeded. Resolved services:
- `postgres`: postgres:16 with pgvector extension
- `redis`: redis:7-alpine with persistence
- `api`: FastAPI application with automatic migration execution on startup
- `worker`: Python RQ worker processing analysis tasks
- `web`: Nginx serving static Vite/React production build and API reverse proxy

## Runtime Result

**ENVIRONMENT-BLOCKED (NOT CLAIMED).** The Docker Desktop daemon service is not running on this host due to unprivileged access controls. Consequently live container spin-up, pgvector extension runtime queries, Redis job queues, and end-to-end containerized HTTP responses remain environment-blocked.

## Required Rerun in Elevated Administrator Environment

When running on an elevated host with Docker Desktop running:

```bash
# 1. Verify Docker daemon is responding
docker info

# 2. Validate Compose configuration
docker compose config

# 3. Build and launch all services in detached mode
docker compose up --build -d

# 4. Check container health
docker compose ps

# 5. Tail service logs
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=200 web

# 6. Verify pgvector extension initialization in PostgreSQL
docker compose exec postgres psql -U changetrace -d changetrace \
  -c "SELECT extversion FROM pg_extension WHERE extname='vector';"

# 7. Check API health endpoint
curl http://localhost:8000/health
```

## Migration & Startup Behavior

`infrastructure/docker/api.Dockerfile` bundles the `infrastructure/migrations` directory and executes the transactional migration runner (`infrastructure/migrations/runner.py`) before starting `uvicorn`. The runner uses advisory concurrency locking (`schema_migration_locks`), applies migrations `001_initial.sql` through `005_github_tenant_and_deliveries.sql` in order, and verifies SHA-256 checksums.
