export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type DecisionStatus = 'GO' | 'REVIEW' | 'BLOCK'
export type SourceLocation = { file: string; line_start: number; line_end: number; symbol?: string }
export type Evidence = {
  id: string; type: string; repository_snapshot_id: string; repository_id: string; commit_sha: string;
  location: SourceLocation; content_hash: string; reason: string; strength: string; quality_score: number;
  snippet: string; status: string
}
export type Component = {
  id: string; type: string; name: string; location: SourceLocation; reason: string;
  evidence_ids: string[]; evidence_strength: string; impact_status: 'CANDIDATE' | 'LIKELY' | 'CONFIRMED' | 'REJECTED'; reasoning_path: string[]
}
export type Risk = {
  risk_id: string; title: string; severity: Severity; risk_score: number; confidence: number;
  claim: string; reasoning: string; evidence: string[]; affected_components: string[];
  recommended_action: string; support_status: string; evidence_strength: string
}
export type Scenario = {
  scenario_id: string; priority: Severity; category: string; behavior: string; actor: string; preconditions: string[];
  action: string; expected_result: string; invariant: string[]; coverage: string; evidence: string[];
  affected_components: string[]; why_missing: string; reason_it_matters: string; related_requirement: string; related_risk?: string
}
export type DiffFile = {
  old_path?: string; new_path?: string; change_kind: string; added_lines: unknown[]; deleted_lines: unknown[];
  symbol_changes: unknown[]; state_changes: { value: string; change_kind: string }[]
}
export type Analysis = {
  analysis_id: string; repository: string; commit_sha: string; snapshot_id: string; analyzer_version: string;
  change_request: string; semantic_analysis: string;
  intent: { entities: string[]; actions: string[]; states_added: string[]; states_removed: string[]; constraints: string[]; expected_behaviors: string[] };
  change_set?: { before_snapshot_id: string; after_snapshot_id: string; before_commit_sha: string; after_commit_sha: string; source: string; files: DiffFile[] };
  graph_delta?: { added_components: string[]; removed_components: string[]; modified_components: string[] };
  impact_summary: Record<string, number>; components: Component[]; candidate_components: Component[];
  graph_edges: { source: string; target: string; relationship: string }[];
  evidence: Evidence[];
  business_rules: { id: string; statement: string; confidence: number; classification: string; evidence_ids: string[] }[];
  state_machines: { id: string; entity: string; states: string[]; transitions: { from_state: string; to_state: string }[] }[];
  contradictions: { id: string; claim: string; confidence: number; evidence_ids: string[] }[];
  risks: Risk[]; test_gaps: Scenario[]; change_plan: string[]; warnings: string[];
  decision: { status: DecisionStatus; rationale: string[]; required_actions: string[] };
}
export type Repository = { id: string; name: string; source_path?: string; github_url?: string; default_branch: string; created_at: string }
