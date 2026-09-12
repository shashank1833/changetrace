# ChangeTrace Testing Assessment

## Scope and current state

This assessment covers the existing modular monolith at `C:/Users/shash/changetrace`. It was prepared before changing analysis behavior or benchmark ground truth. The repository has no initial Git commit; every project file is currently untracked. That prevents commit-to-commit regression attribution until an initial baseline is committed.

ChangeTrace has two distinct correctness obligations:

1. **Software correctness:** parsing, API behavior, persistence, authorization, queueing, rendering, exports, and failures work as specified.
2. **Analysis correctness:** reported impacts, rules, evidence, risks, test gaps, contradictions, and decisions correspond to actual repository behavior.

The existing suite establishes useful software invariants, but the controlled benchmark reports poor analysis precision: impact `0.1857`, evidence `0.0982`, risk `0.4848`, and test-gap `0.1569`. These values must not be interpreted as general repository accuracy.

## Current test architecture

- **Unit:** interpreter, repository extraction, diff path rejection/basic parsing, risk-score boundaries, evidence quality ordering, state extraction, contradictions, prompt-injection isolation, tenant helper behavior, and verifier relationships.
- **Integration:** deterministic pipeline, proposed-diff graph delta, API report/feedback behavior.
- **Evaluation:** one recall assertion plus a 33-scenario benchmark over one small e-commerce fixture.
- **E2E:** one Playwright happy path covering repository selection through decision/export controls.
- **Security:** security-oriented cases currently live under `tests/unit`; there is no dedicated `tests/security` suite.
- **Adversarial/property/reliability/performance/cross-domain:** no dedicated suites yet.
- **CI:** Ruff, mypy, pytest with coverage threshold, frontend build, Playwright, npm audit, pip-audit, benchmark execution, and Compose configuration validation are configured.

## Current benchmark architecture

`tests/evaluation/benchmark/run.py` executes `AnalysisPipeline` independently for 33 natural-language requests against `tests/evaluation/demo_repository`. It compares sets of result file paths or category strings against scenario labels and micro-aggregates counts.

Current benchmark labels include:

- expected affected file paths;
- expected important evidence file paths;
- required substrings in the single generated risk title/claim;
- expected generated test-gap category names;
- a sparse list of known false-positive files.

Important limitations:

- All 33 scenarios use one e-commerce repository; scenario records have no `domain`.
- Scenarios do not include proposed diffs despite diff support being a core input.
- Ground truth does not distinguish `DIRECTLY_AFFECTED`, `TRANSITIVELY_AFFECTED`, `POTENTIALLY_RELATED`, and `IRRELEVANT`.
- Ground truth has no expected contradiction field and no claim-specific evidence relationship.
- Evidence is scored by unique file path, not whether a source range supports a particular claim.
- Risk “true positives” are required-word matches in generated text. There is no risk recall, severity correctness, or expert-adjudicated semantic match.
- Test gaps are category matches. Existing or partial coverage is not comprehensively labeled.
- False-positive rate measures only explicitly listed `known_false_positives`; those lists are incomplete in most scenarios.
- Unsupported-claim rate checks only that risk evidence IDs exist in the result. It does not establish that evidence semantically supports the claim.
- Per-category precision/recall/F1, evidence validity rate, and schema-valid output rate are not reported.
- The runner always writes `results.json`; it has no immutable baseline mode.

The benchmark is useful as a controlled regression fixture, but it is not yet sufficient to establish client trust or cross-domain generalization.

## Current failure modes

### Impact discovery

1. **Every lexical match is promoted to a confirmed component.** `ImpactEngine.discover` has no candidate/likely/confirmed/rejected status. A single identity or snippet match becomes a distance-zero impact.
2. **Broad source text creates broad seeds.** Full function/class snippets are searched, so incidental literals, comments, and called names can seed a component.
3. **Prefix matching conflates concepts.** The pattern `term\w*` allows `return` to match `returned` and unrelated language uses such as “return a value.”
4. **Generic intent extraction is only partially filtered.** Domain words that occur almost everywhere in the fixture continue to seed many files.
5. **Traversal is effectively bidirectional.** `impact_neighborhood` follows incoming and outgoing dependency edges, enabling callers and callees to spread without causal direction being represented in the finding.
6. **File membership broadens results.** Seed file nodes may expand through `CONTAINS`; member nodes also add containing files. File and symbol impacts are then collapsed to file-level benchmark results.
7. **Call resolution is name-only and repository-global.** Two similarly named symbols can be connected without module/import disambiguation.
8. **JavaScript call extraction is regex-based and assigns the file as caller.** Strings/comments and similarly named calls can create weak edges.
9. **Import resolution uses substring matching.** Imported module text can match unintended paths.
10. **No dead-code/reachability model exists.** An unused legacy component can be promoted from lexical similarity.
11. **Documentation, tests, and implementation components share the same impact promotion path.** Relationship semantics do not constrain impact class.
12. **Proposed-diff inclusion promotes every indexed component in a changed file**, not only changed symbols or dependency-relevant members.

### Evidence selection

1. **Evidence selection is component selection.** `EvidenceEngine.collect` copies every selected component's primary evidence; it performs no claim-specific relevance check.
2. **Evidence strength is inherited from graph distance**, not from whether the excerpt proves the claim.
3. **Quality scores are fixed mostly by strength.** Hash validity and nonempty snippets can produce a high score even when the excerpt only proves existence.
4. **Risk evidence is the first 12 component evidence IDs**, while the risk claim is generic or refund-specific. There is no claim-to-evidence entailment or required behavioral term check.
5. **Test-gap evidence is the first six affected-component evidence IDs**, reused for every scenario regardless of category.
6. **The verifier validates references, snapshots, hashes, and score reproducibility, but not semantic support.** Consequently, structural unsupported-claim rate can remain zero while evidence precision is about ten percent.

### Test-gap discovery

1. A largely fixed catalog of five to ten scenarios is generated for any nonempty impact set.
2. Coverage is inferred from test names only; assertions, fixtures, parametrization, called production symbols, and integration coverage are not analyzed.
3. Lack of a lexical name match becomes `MISSING_TEST`; uncertainty is not represented. The schema has no `UNCERTAIN` coverage status.
4. Generic authorization/state/boundary gaps are emitted even when the change intent does not require those behaviors.
5. Every scenario receives the same broad evidence and component list.

### Risk and decision

1. Dependency impact increases with component count and boundary-type count, so false-positive impacts directly inflate risk.
2. State-transition uplift counts all discovered transitions rather than transitions affected by this change.
3. Test-gap factor uses a pre-analysis heuristic (`max(1, 5 - affected tests)`) rather than final coverage evidence.
4. Criticality is based on substring presence across selected component names.
5. One generic risk is emitted for every nonempty impact set, including potentially trivial or documentation-only changes.
6. Confidence rises with evidence count even if the evidence is irrelevant.
7. The adversarial verifier compares long words in risk titles to test names; it does not inspect assertions.

### State machines and contradictions

- State-machine extraction recognizes Python enum assignments and literal transition containers only. Side effects and transition-specific tests are not mapped.
- Transition evidence is attached to the enclosing function, not necessarily the exact transition literal.
- Contradiction detection is a conservative lexical heuristic over selected docs/code. It does not model propositions, and it cannot currently represent docs-vs-tests-vs-code triads reliably.

### Software, reliability, and security gaps

- Diff tests omit malformed hunks, absolute paths, rename/delete/add semantics, binary leakage, symlink behavior, and many API/DB changes.
- Snapshot tests omit stale/missing provenance, invalid refs, archive failures, cleanup, symlink and extraction attacks.
- Analyzer tests are broad type-presence assertions rather than exact dependency and false-positive assertions.
- Graph direction, duplicate edges, cycles, depth, and relationship-type semantics lack direct tests.
- LLM tests do not cover malformed JSON, provider/rate-limit/timeout failures, unknown evidence IDs, or oversized responses. The production pipeline currently makes zero LLM calls.
- API tests do not comprehensively cover oversized requests, malformed diffs, concurrency, rate limiting, all tenant-owned resources, WebSockets, or status codes.
- Development header identity is trusted directly and is not production authentication.
- GitHub cloning allows only `https://github.com/`, reducing SSRF scope, but tokenized URLs can appear in Git subprocess diagnostics unless carefully redacted.
- Repository scanning has no explicit per-file/total-size bounds and follows ordinary files reachable by recursive traversal; dangerous symlink and resource-exhaustion behavior needs verification.
- There is no measured 1K/10K/50K/100K performance baseline, memory profile, repeatability suite, or queue-load test.
- Docker runtime remains unverified because the Linux daemon was unavailable in the previous attempt.

## Likely false-positive categories

The code inspection predicts these dominant categories, to be quantified from raw benchmark outputs before fixes:

- naming/prefix similarity;
- broad snippet lexical matches;
- import-only or weak import path matching;
- bidirectional/transitive graph expansion;
- file/symbol containment expansion;
- test and documentation relationships treated as impact;
- shared state/database/business vocabulary;
- dead code and disconnected lexical matches;
- generic fixed test scenarios;
- evidence of existence incorrectly treated as evidence of a claim.

The current benchmark result file does not contain enough raw predictions or reasoning paths to calculate a defensible category breakdown. The runner must first preserve raw component/evidence/edge/scenario outputs or an audit table must be generated without changing labels.

## Ground-truth gaps

A rigorous scenario needs immutable expert labels for:

- domain and change category;
- optional proposed diff;
- direct, transitive, potential, irrelevant, and dead components;
- expected causal paths and allowed relationship types;
- claim-specific evidence source ranges and acceptable alternatives;
- expected business rules, transitions, contradictions, and absence cases;
- risks with severity and required support;
- coverage as covered/partial/missing/uncertain/contradicted;
- explicit negative expectations;
- adjudication notes and label version.

Existing labels will not be silently modified to make metrics improve. Any schema enrichment must preserve the original labels and record rationale/version separately.

## Proposed adversarial strategy

1. Freeze the current benchmark output as `baseline_results.json` and run all existing checks.
2. Enhance benchmark diagnostics first: emit F1, category metrics, raw predictions, and false-positive candidates without changing expected labels.
3. Manually audit every predicted file/evidence relationship for representative scenarios and classify the causal defect.
4. Add focused unit regressions for each demonstrated defect before changing production logic.
5. Introduce an explicit impact disposition (`CANDIDATE`, `LIKELY`, `CONFIRMED`, `REJECTED`) or equivalent verified output contract; lexical similarity alone must remain candidate-level.
6. Make graph propagation relationship-aware and directional, with import/call disambiguation and dead-code handling.
7. Make evidence claim-specific. Separate evidence of component existence, dependency, business rule, and risk claim.
8. Analyze test bodies/assertions and affected symbols; classify uncertainty separately from missing coverage.
9. Decouple risk from raw graph breadth and validate trivial, test-only, docs-only, high-impact/low-confidence, and irrelevant-node metamorphic cases.
10. Add dedicated adversarial, security, property/metamorphic, API, report, determinism, and performance suites.
11. Add a second ticketing/subscription fixture and report each domain separately; do not introduce domain-specific analyzer rules.
12. Execute the complete RETURNED diff flow through API, worker mode available locally, persistence, exports, and UI.
13. Attempt Docker runtime verification and record the exact daemon/runtime outcome.
14. Publish before/after precision and recall with all regressions and unresolved defects.

## Quality targets (not current facts)

- Impact precision > `0.70`
- Evidence precision > `0.75`
- Risk precision > `0.70`
- Test-gap precision > `0.70`
- Unsupported structural claims = `0`
- Evidence validity = `1.0`
- Schema-valid output = `1.0`

These are engineering targets, not acceptance claims. Failure to reach them will be reported rather than hidden or achieved by relabeling the fixture.
