# Engine & Analysis Service Contracts

> [!NOTE]
> ChangeTrace rejects "multi-agent" marketing buzzwords. All core components are deterministic, bounded, schema-constrained Python analysis engines operating inside a synchronous, fail-closed verification pipeline.

## Change Interpreter Contract
Input: request text and optional unified Git diff. Output: strict `ChangeIntent`. It may not invent source locations. Fallback uses deterministic multi-domain keyword and structure extraction.

## Business Rule & Contradiction Discovery
Input: extracted condition/state structures and verified evidence IDs. Output: statement, `EXPLICIT|INFERRED|UNCERTAIN|CONTRADICTORY`, confidence, source locations, snapshot, and evidence IDs. Inferred rules are never displayed as confirmed facts.

## Risk Reasoning Engine
Input: immutable deterministic factors, affected component IDs, state transitions, and allowed evidence. Output: explanation and component-specific action only. It cannot alter numeric scores, severity boundaries, commit SHAs, or evidence hashes.

## Test Gap Generator
Input: intent, rules, affected boundaries, existing tests, and allowed evidence. Output: derived scenario specifications (`COVERED`, `MISSING`, `CONTRADICTED`). It must deduplicate scenarios and avoid count inflation.

## Adversarial Verifier
Input: calculated risks plus supporting and candidate counter-evidence (existing tests, guards). Output: `SUPPORTED|WEAKLY_SUPPORTED|CONTESTED|INSUFFICIENT_EVIDENCE` and bounded confidence adjustment. It cannot remove provenance.

## Pipeline Release Gate (Decision Engine)
Input: verified risks, test gaps, contradictions, and actionable change plan. Output: deterministic `GO`, `REVIEW`, or `BLOCK` decision. No probabilistic model chooses the release decision.

## Global Invariants

No service has unrestricted repository authority or network access. Repository comments/docs are untrusted data. All outputs use strict Pydantic schemas and allowed evidence IDs. The core production path is deterministic, reproducible, and verifiable.
