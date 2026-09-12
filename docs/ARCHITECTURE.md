# Architecture

## System flow

```text
React / React Query / React Flow
              ↓ REST + job polling/WebSocket
FastAPI / tenant authorization / audit
              ↓
Analysis orchestrator → Redis/RQ worker (inline fallback locally)
              ↓
Change Interpreter + Repository Intelligence + Diff Analyzer
              ↓
Before Index/Graph → ChangeSet/GraphDelta → After Index/Graph
              ↓
Impact + State Machines + Business Rules + Contradictions
              ↓
Evidence Graph → Deterministic Risk → Test Gaps
              ↓
Adversarial Review → Verification → GO / REVIEW / BLOCK
              ↓
PostgreSQL + pgvector
```

## Why a modular monolith

The workflow requires shared transactions, schemas, and evidence invariants more than independent deployment. Domain services remain separate Python modules while API and worker share one release. Extracting microservices now would add distributed failure modes without improving simulation quality.

## Technology decisions

- **PostgreSQL:** tenant-scoped durable metadata, jobs, snapshots, evidence, results, and feedback with relational integrity.
- **pgvector:** reserved for semantic candidate retrieval. Candidates can never become facts without source evidence.
- **Python AST / Tree-sitter direction:** Python AST is the reliable implemented parser; TS/JS patterns are baseline support. Optional Tree-sitter packages define the path to uniform cross-language syntax extraction.
- **NetworkX:** bounded in-memory traversal and before/after graph comparison without operating a graph database.
- **Deterministic + AI hybrid:** parsing, diffs, locations, hashes, graph deltas, scores, and decisions are deterministic. AI is provider-neutral, schema-constrained, and currently optional/degraded.

## Snapshot and diff architecture

Current/base source is independently indexed. Unified patches are parsed without an LLM, path-validated, and applied to an isolated copy without executing repository code. Branch/commit refs are character-restricted, resolved to SHAs, and materialized with `git archive`. Stable `type:file:symbol` keys identify added, removed, and modified graph nodes. Evidence displayed to users belongs to the after/proposed snapshot and its exact content hash.

## Evidence and trust boundary

```text
untrusted source → deterministic extraction → immutable evidence
→ constrained reasoning → adversarial search → fail-closed verifier → user
```

Evidence records repository, snapshot, commit, file, lines, symbol, type, reason, strength, quality, hash, and status. Risk, confidence, and evidence strength are separate. Unknown IDs, stale hashes, cross-snapshot evidence, invalid components, non-reproducible scores, and duplicate finding IDs fail verification.

## Failure handling

Parser failures become warnings. Model failures preserve deterministic output and mark semantic analysis degraded. Invalid patches fail before analysis persistence. Worker failures persist a FAILED job and RQ retries bounded failures. Evidence mismatch requires reanalysis. Full analysis remains the fallback until incremental correctness is proven.

## Security boundaries

Repository content is data, never instructions or executable input. Patch paths and Git refs are validated. Local paths are root-confined. LLMs receive no repository by default and have no tools. Source is excluded from normal logs. REST resources are tenant-filtered; production must replace development headers and secure WebSocket authentication.

## Scaling strategy

First improve benchmark precision. Next cache immutable indexes by snapshot, calculate changed neighborhoods, and use full fallback for removals/parser uncertainty. Scale API and RQ workers horizontally against managed PostgreSQL/Redis; keep the modular monolith until measured queue or compute boundaries justify extraction.
