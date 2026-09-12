# Evaluation Results

## Run

- Date: 2026-09-09
- Analyzer: `0.2.0`
- Fixture: controlled e-commerce repository in `tests/evaluation/demo_repository`
- Definitions: `tests/evaluation/benchmark/scenarios.json`
- Scenarios: 33
- Command: `python tests/evaluation/benchmark/run.py`
- Machine-readable output: `tests/evaluation/benchmark/results.json`

## Measured baseline

| Metric | Result |
|---|---:|
| Impact precision | 0.1857 |
| Impact recall | 0.9541 |
| Evidence precision | 0.0982 |
| Evidence recall | 0.9821 |
| Risk precision | 0.4848 |
| Test-gap precision | 0.1569 |
| Test-gap recall | 0.9808 |
| Known false-positive detection rate | 1.0000 |
| Unsupported-claim rate | 0.0000 |
| Median analysis duration | 0.153 s |

## Interpretation

These results are a baseline for this synthetic fixture only. They are not general repository-analysis accuracy.

Recall is high because lexical matching and two-hop traversal are intentionally broad. Precision is low: the engine frequently includes additional components and generic test scenarios. Every generated risk had valid evidence IDs, producing a measured unsupported-claim rate of zero under the benchmark's structural definition; that does not prove that every claim is semantically correct.

The benchmark therefore confirms the immediate engineering priority: improve ranking and causal graph precision without sacrificing evidence validity. It does **not** justify production accuracy claims.

## Method limitations

- Expected labels are file-level, while the analyzer emits file and symbol components. Precision aggregates unique files.
- Risk labels currently use required claim terms, not expert adjudication of complete risk semantics.
- Test-gap precision compares generated categories with expected categories; it does not inspect generated assertions.
- Evidence precision uses labeled important files, not line-by-line human review.
- Known false-positive rate uses explicit negative-control files and is not a complete false-positive census.
- All scenarios share one compact synthetic repository and are not statistically independent.

## Next evaluation work

1. Independently review labels and each evidence line.
2. Split scenarios into tuning and held-out sets.
3. Add realistic multi-service TypeScript and Python fixtures.
4. Label risk support and test assertions, not only keywords/categories.
5. Add diff-specific scenarios for additions, deletions, renames, API/SQL changes, and lost test coverage.
6. Report latency distributions on fixed hardware and repository sizes.
