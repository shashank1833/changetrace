# Product Requirements

ChangeTrace is a Business Change Simulator for engineering teams. It answers before implementation: what changes, what is affected, why, what evidence supports that conclusion, what could break, which tests are missing, and whether to go, review, or block.

## Core input and output

Input is a repository snapshot, natural-language requirement, and optional unified diff or base/target refs. Output is a before/after change set, graph delta, impact summary, state machines/business rules, immutable evidence, deterministic risks with separate confidence/evidence strength, test gaps, contradictions, plan, and policy decision.

## Acceptance

- No source claim without valid evidence.
- Every evidence item identifies repository, snapshot, commit, file, lines, symbol, reason, strength, quality, and hash.
- Diff structure and numeric risk are deterministic.
- Model failure does not prevent deterministic analysis.
- Inferred/contradictory/uncertain rules are visibly classified.
- Tenant checks execute server-side.
- The expanded benchmark is measured and its limitations disclosed.

## Non-goals

No generic code review, code generation, CMDB, APM, project management, broad connector marketplace, or autonomous repository execution.
