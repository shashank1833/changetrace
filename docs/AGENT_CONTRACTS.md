# Agent Contracts

## Change Interpreter
Input: request text and optional deterministic diff summary. Output: strict `ChangeIntent`. It may not invent source locations. Malformed output retries once and falls back to deterministic extraction.

## Business Rule Discovery
Input: extracted condition/state structures and allowed evidence IDs. Output: statement, `EXPLICIT|INFERRED|UNCERTAIN|CONTRADICTORY`, confidence, source locations, snapshot, and evidence IDs. Inferred rules are never displayed as confirmed facts.

## Risk Reasoning
Input: immutable deterministic factors, affected component IDs, state transitions, and allowed evidence. Output: explanation and action only. It cannot alter numeric score, severity boundaries, commit, or evidence.

## Test Gap Generator
Input: intent, rules, affected boundaries, existing tests, and allowed evidence. Output: actor/preconditions/action/result/invariant/requirement/components/evidence/coverage. It must deduplicate scenarios and avoid count inflation.

## Adversarial Reviewer
Input: risk plus supporting and candidate counter-evidence. Output: `SUPPORTED|WEAKLY_SUPPORTED|CONTESTED|INSUFFICIENT_EVIDENCE` and bounded confidence adjustment. It cannot remove provenance.

## Explanation Generator
Input: already verified finding and reasoning path. Output: concise user-facing explanation. It cannot add components, evidence, or facts.

## Global controls

No agent has tools or unrestricted repository authority. Repository comments/docs are untrusted data. Calls have structured output, schema validation, timeout, bounded retries, provider/model/prompt version, usage metadata, and failure handling. Prompts/source are not written to general logs. Unknown evidence IDs invalidate output. The current production path uses deterministic fallbacks and marks semantic analysis degraded.
