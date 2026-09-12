# Docker Runtime Verification

## Environment

- Date: 2026-09-12
- Host: Windows, Docker context `desktop-linux`
- Docker CLI: 29.6.2
- Docker Compose: v5.3.1

## Commands and actual results

`docker info` returned:

```text
Client:
 Version: 29.6.2
 Context: desktop-linux
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine:
The system cannot find the file specified.
```

`docker compose config` succeeded. Resolved services are `postgres`, `redis`, `api`, `worker`, and `web`. Ordered SQL migrations are mounted read-only at `/docker-entrypoint-initdb.d` and therefore initialize only a new isolated PostgreSQL volume.

## Runtime result

**NOT VERIFIED.** Docker Desktop's Linux daemon was not running. Consequently image builds, pgvector extension availability, service health, Redis/RQ job consumption, PostgreSQL persistence, API retrieval, and frontend display were not claimed.

## Required rerun

```bash
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=200 web
docker compose exec postgres psql -U changetrace -d changetrace \
  -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
curl http://localhost:8000/health
```

Then submit `/workspace/demo`, the RETURNED request, and a proposed patch through the API/UI. Confirm from worker logs that RQ consumed the job and verify retrieval from PostgreSQL.

## Migration behavior

The pgvector image is configured and `001_initial.sql` creates the extension. Compose mounts the ordered migration directory into PostgreSQL's initialization directory, so migrations run for a newly created verification volume. Existing volumes are intentionally not deleted or silently migrated; operators must apply newer SQL migrations explicitly.
