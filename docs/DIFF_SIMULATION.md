# Diff-aware Simulation

## Inputs

A change request may include either:

- a unified Git patch in `proposed_diff`, or
- both `base_ref` and `target_ref` for a local Git repository.

These options are mutually exclusive and validated by `ChangeCreate`.

## Deterministic flow

1. Resolve the current/base snapshot and commit.
2. Parse `diff --git` file headers and hunk line numbers without an LLM.
3. Reject binary patches and traversal paths.
4. Materialize the proposed tree in a temporary directory with `git apply`; repository code is never executed.
5. Index before and after trees independently.
6. Compare stable component keys (`type:file:symbol`) and exact component source to derive added, removed, and modified nodes.
7. Compare stable relationship tuples to derive graph edges added or removed.
8. Seed impact analysis with changed files/components in addition to natural-language terms.
9. Bind all displayed source evidence to the after snapshot and proposed commit hash.
10. Delete temporary worktrees after verified result construction.

For branch/commit comparisons, refs are restricted to Git ref characters, resolved to commit SHAs, and the base tree is exported with `git archive`. The target patch is then applied to that base tree. No checkout mutates the source repository.

## Output

`AnalysisResult.change_set` contains file line/symbol/state/API/database/SQL deltas. `graph_delta` contains stable added, removed, and modified components plus relationship deltas. No-diff requests preserve the original current-state analysis path and return both fields as null.

## Limitations

- Modified lines are represented as adjacent additions/deletions rather than an edit-distance pairing.
- Rename support depends on Git diff rename headers.
- TypeScript symbol extraction remains conservative regex-based analysis.
- Proposed evidence is tied to a synthetic `proposed-<patch hash>` commit identity, not an actual Git object.
- Temporary directories are cleaned after analysis; the validated evidence snippet is persisted, but source navigation to a proposed file requires the client-supplied patch.
