# Threat Model

## Assets

Private source and diffs, GitHub installation tokens, organization identity, snapshots, evidence snippets, model context, findings, and user feedback.

## Controls

- **Cross-tenant access:** server-side organization predicates and non-disclosing 404s; evidence is authorized through a tenant-owned analysis. PostgreSQL RLS remains defense-in-depth work.
- **Diff/path attacks:** unified-diff paths reject absolute/traversal paths; binary patches are rejected; proposed trees are isolated temporary copies.
- **Malicious repositories:** source is parsed, never imported or executed; generated/vendor directories are ignored. Resource limits and parser process isolation remain production gates.
- **Git abuse:** refs use a strict character allowlist and resolve to commits; branch comparison uses `git archive` and `git diff` without repository hooks or checkout mutation.
- **Prompt injection/tool abuse:** source/docs are untrusted data; agents have no tools; outputs use strict schemas and allowed evidence IDs; deterministic verification is authoritative.
- **Source exfiltration:** only minimum evidence context may reach an external model; normal logs/traces exclude source and prompts.
- **Stale evidence:** snapshot/commit and SHA-256 are verified before display.
- **Credentials:** use short-lived least-privilege GitHub App tokens and a secret manager. Current demo has no production token lifecycle.
- **Abuse/DoS:** request size limits, patch size validation, timeouts, bounded traversal/retries, tenant quotas, and distributed rate limiting are required. Current limiter is process-local.
- **Feedback integrity:** feedback is tenant/analysis/finding scoped and audited; it does not automatically retrain models.

## Production gates

Replace header auth, authenticate WebSockets, encrypt credentials, run migrations, enable RLS, sandbox parsing with CPU/memory/file limits, configure egress restrictions, add secret/SAST/SBOM/container scanning, define retention/deletion, and complete Docker runtime verification.
