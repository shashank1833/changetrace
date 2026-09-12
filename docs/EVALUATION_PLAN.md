# Evaluation Plan

The controlled e-commerce fixture covers direct and indirect dependencies, business rules, SQL constraints, jobs, integrations, authorization, state transitions, missing tests, contradictory documentation, negative controls, dead code, ambiguous naming, cross-module behavior, idempotency, rollback, consistency, and API contracts.

Ground truth is in `tests/evaluation/benchmark/scenarios.json`. It contains 33 scenarios and the required labels: expected affected files, business-rule terms, important evidence files, risk terms, test-gap categories, and known false positives.

## Metrics

- Impact precision/recall compare unique affected files with expected files. Scenarios may additionally use `expected_findings` entries containing file, symbol, component type, causal relationship, and minimum classification. These stricter labels prevent an unrelated symbol in the correct file from receiving credit. Legacy file labels remain supported until each scenario is independently adjudicated; labels must not be migrated solely to change a score.
- Evidence precision/recall compare unique evidence files with important evidence labels.
- Risk precision requires expected risk terms to appear in emitted risk claims/titles.
- Test-gap precision/recall compare missing scenario categories.
- Known false-positive rate measures explicitly labeled negative-control files.
- Unsupported-claim rate checks that every risk references evidence present in the verified result.
- Median latency uses the pipeline's measured duration.

Run:

```bash
python tests/evaluation/benchmark/run.py
```

The runner writes `tests/evaluation/benchmark/results.json`. See `EVALUATION_RESULTS.md` for the latest actual run.

## Independent subscription-billing domain

`tests/evaluation/cross_domain` contains a separate 15-scenario subscription-billing fixture. It covers authorization, state transitions, business rules, payment retry, notification, idempotency, rollback, API contracts, background jobs, persistence constraints, integration failures, contradictory documentation, dead code, ambiguous terminology, and irrelevant code. Run it with:

```bash
python tests/evaluation/cross_domain/run.py
```

Its labels were authored before execution and retain explicit irrelevant controls. The initial results intentionally expose cross-domain over-selection rather than relabeling findings to improve scores.

These labels are development benchmarks, not general accuracy. The next methodology step is independent expert adjudication and held-out real repositories.
