# REST API Specification

Base `/api/v1`; JSON; OpenAPI at `/docs`. Every persisted resource lookup is organization-scoped. Development headers are an adapter, not production authentication.

## Repositories

- `POST /repositories` — `{name, source_path? | github_url?, default_branch}`
- `GET /repositories`
- `GET /repositories/{id}`
- `POST /repositories/{id}/sync` — creates/returns immutable snapshot identity

## Changes and analysis

- `POST /changes` — `{repository_id, description, proposed_diff?, base_ref?, target_ref?}`
  - `proposed_diff` and ref comparison are mutually exclusive.
  - `base_ref` and `target_ref` must be supplied together.
- `GET /changes`; `GET /changes/{id}`
- `POST /changes/{id}/analyze` — `202 JobView`
- `GET /jobs/{id}`; `WS /jobs/{id}/events`
- `GET /analyses/{id}`; `GET /analyses/{id}/status`

Job states: `QUEUED`, `INGESTING`, `PARSING`, `INDEXING`, `IMPACT_ANALYSIS`, `RISK_ANALYSIS`, `TEST_GAP_ANALYSIS`, `VERIFICATION`, `COMPLETED`, `FAILED`.

## Artifacts and decisions

- `GET /changes/{id}/impact`
- `GET /changes/{id}/risks`; `GET /risks/{id}`
- `GET /evidence/{id}`
- `GET /changes/{id}/test-gaps`
- `GET /changes/{id}/plan`
- `GET /analyses/{id}/report?format=json|markdown`
- `POST /analyses/{id}/findings/{finding_id}/feedback` — `{decision: CONFIRM|REJECT|NOT_RELEVANT, reason?}`

Errors use `{detail}`. Missing and cross-tenant resources return 404. Writes reject viewer roles. The report contains analysis artifacts but no credentials.
