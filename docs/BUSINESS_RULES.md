# Business Rules and State Machines

## Rules

Python conditional expressions containing domain indicators such as status, permission, eligibility, or inspection are extracted deterministically. Rules are currently represented as **INFERRED**, not confirmed facts, and retain evidence IDs, source locations, snapshot identity, confidence, and status.

## State machines

`StateMachineAnalyzer` discovers enum-like Python state classes and literal transition maps. Its reusable representation contains entity, states, valid transitions, handlers, side effects, evidence, and snapshot. It does not assume e-commerce names; the included fixture happens to model order states.

A proposed state is also detected from changed enum assignments in a Git patch. Before/after graph comparison then records the added state component. The risk engine uses affected transition count as a bounded deterministic uplift while preserving the documented baseline score.

## Contradictions

The contradiction detector is deliberately conservative. It requires:

1. documentation evidence containing an explicit negation/prohibition;
2. implementation/test/rule evidence sharing multiple normalized behavior terms; and
3. two valid evidence IDs in the same result.

Outputs are labeled `CONTRADICTORY`, include confidence, and explicitly require manual confirmation. The detector does not treat arbitrary semantic similarity as proof.

## Known limits

- Transition extraction currently recognizes literal Python dictionaries of sets/lists/tuples.
- Side-effect association is not yet complete.
- Documentation normalization is lexical and can miss paraphrases.
- Cross-language state machines require Tree-sitter query support.
