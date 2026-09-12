# Security and Independent Evaluation

## Threat model

Repository files, comments, documentation, diffs, model responses, tenant identifiers, and request metadata are untrusted. Repository content is indexed as data and is never executed or promoted to instructions. The deterministic result verifier remains authoritative over optional model output.

## Adversarial coverage

- Repository prompt injection in Markdown, comments, docstrings, and source strings.
- Diff traversal, absolute paths, duplicate entries, binary/NUL content, malformed patches, oversized lines, excessive patch size, and unsafe Git refs.
- Evidence with nonexistent files/symbols, invalid ranges/hashes, wrong snapshots/repositories, or claim-incompatible text.
- Cross-tenant repository, change, job, analysis, evidence, and finding access.
- Secret leakage through provider errors, job errors, reports, and API responses.
- Rate limiting and security headers, including rejected responses.
- Invalid, fabricated, missing, and oversized structured model output.
- Decision safety: unsupported or semantic-only risks cannot cause BLOCK.

## Fixes from red-team review

- Diff parsing now rejects duplicate file entries, patches over 2 MB, lines over 100 KB, and NUL/binary-looking content before materialization.
- Model responses over 64 KB fail closed before JSON/schema validation.
- Rate-limit responses receive the same security headers as successful responses.
- Persisted analysis-job errors use a generic message; detailed exceptions remain server-side and are correlated by job ID.
- BLOCK considers only supported risks with non-semantic evidence and referenced components. Its rationale includes the supporting evidence-reference count.

## Subscription billing benchmark

`tests/evaluation/cross_domain` is an independent controlled domain with 15 scenarios covering authorization, state transitions, business rules, payment retries, notification, idempotency, rollback, API contracts, jobs, persistence, integration failure, contradictory documentation, dead code, ambiguous terminology, and irrelevant code.

Measured command: `python tests/evaluation/cross_domain/run.py`

- Impact precision: 0.3303
- Impact recall: 0.8571
- Evidence precision: 0.1651
- Evidence recall: 0.8571
- Test-gap precision: 0.3750
- Test-gap recall: 0.6818
- Explicit irrelevant-selection rate: 0.4286
- Unsupported-claim rate: 0.0000
- Median duration: 0.092 s

The poor precision is retained as an honest cross-domain baseline. It indicates that the analyzer remains overfit to broad lexical/domain matches when many subscription components share the word `subscription`.

The evaluator deduplicates findings by file and supports structured expectations for file, symbol, component type, causal relationship, and minimum classification. Candidates do not count as impacts. Evidence and unsupported-claim metrics are reported separately.

This benchmark is synthetic. It does not establish production accuracy, real-world security, or statistical generalization. Labels require independent review before structured migration and must not be changed solely to improve scores.
