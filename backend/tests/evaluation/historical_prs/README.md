# Historical PR Evaluation Harness

## Purpose & Scope

The Historical PR Evaluation Harness verifies ChangeTrace's core value proposition: **evaluating real proposed Git diffs against existing repository states and producing accurate, explainable release decisions (`GO`, `REVIEW`, `BLOCK`) before code merges to main.**

Unlike static snapshot analysis, PR evaluation simulates the exact GitHub workflow:
1. Parse unified diff format into before/after line changes and symbol modifications.
2. Materialize the temporary "after" repository tree without executing unverified code.
3. Compute AST and graph deltas comparing symbol reachability, state transitions, and API/DB contracts.
4. Calculate risk scores and identify test gaps introduced by the patch.
5. Apply the release policy to deliver deterministic release decisions with itemized `+` (positive) and `-` (mitigating) drivers.

## Historical Scenarios

The harness tests 5 representative historical pull request patterns across multiple domains:

| ID | Domain | Category | Description | Expected Decision |
|---|---|---|---|:---:|
| `pr-01-order-state-invalidation` | E-Commerce | `state_machine_transition` | PR #104: Adds `RETURNED` state to `OrderStatus` enum without updated transition guards | **REVIEW** |
| `pr-02-fintech-fee-surcharge-break` | Fintech | `financial_calculation` | PR #215: Adds multi-currency fee surcharge affecting settlement calculations | **REVIEW** |
| `pr-03-fintech-missing-settlement-guard` | Fintech | `authorization_bypass` | PR #288: Allows direct settlement from `INITIALIZED` status, bypassing authorization | **REVIEW** |
| `pr-04-safe-additive-order-utility` | E-Commerce | `safe_additive_refactor` | PR #312: Adds tracking code string formatter utility without state or schema mutations | **GO** |
| `pr-05-subscription-pause-state` | Billing | `subscription_lifecycle` | PR #405: Adds `PAUSED` state to `SubscriptionStatus` enum without pause/resume handlers | **REVIEW** |

## Execution

Run the evaluation runner directly:
```bash
python tests/evaluation/historical_prs/run.py
```

Rebuild scenarios from base repositories and validated Git diffs:
```bash
python tests/evaluation/historical_prs/build_scenarios.py
```

## Results & Quality Assertions

The runner produces machine-readable metrics in `tests/evaluation/historical_prs/results.json` and enforces:
- `diff_patch_validity_rate == 1.0` (all PR patches apply cleanly via `git apply`)
- `decision_accuracy >= 0.80` (release decision matches verified ground truth)
- `unsupported_claim_rate == 0.0` (zero ungrounded risks)
- `evidence_validity_rate == 1.0` (100% hash, range, and provenance valid)
