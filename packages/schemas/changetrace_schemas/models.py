from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class ComponentType(StrEnum):
    FILE = "FILE"
    MODULE = "MODULE"
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    API = "API"
    DATABASE = "DATABASE"
    JOB = "JOB"
    INTEGRATION = "INTEGRATION"
    TEST = "TEST"
    DOCUMENT = "DOCUMENT"
    STATE = "STATE"
    STATE_TRANSITION = "STATE_TRANSITION"
    BUSINESS_RULE = "BUSINESS_RULE"


class EvidenceStrength(StrEnum):
    DIRECT = "DIRECT"
    STRONG = "STRONG"
    INDIRECT = "INDIRECT"
    SEMANTIC = "SEMANTIC"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"


class ImpactStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    LIKELY = "LIKELY"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ChangeKind(StrEnum):
    ADDED = "ADDED"
    DELETED = "DELETED"
    MODIFIED = "MODIFIED"
    RENAMED = "RENAMED"


class DecisionStatus(StrEnum):
    GO = "GO"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class EvidenceType(StrEnum):
    CODE_REFERENCE = "CODE_REFERENCE"
    TEST_REFERENCE = "TEST_REFERENCE"
    DB_REFERENCE = "DB_REFERENCE"
    API_REFERENCE = "API_REFERENCE"
    DOCUMENT_REFERENCE = "DOCUMENT_REFERENCE"
    GRAPH_RELATIONSHIP = "GRAPH_RELATIONSHIP"
    RUNTIME_REFERENCE = "RUNTIME_REFERENCE"
    BUSINESS_RULE = "BUSINESS_RULE"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleClassification(StrEnum):
    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"
    CONTRADICTORY = "CONTRADICTORY"


class CoverageStatus(StrEnum):
    COVERED = "COVERED"
    PARTIALLY_COVERED = "PARTIALLY_COVERED"
    MISSING = "MISSING"
    UNCERTAIN = "UNCERTAIN"
    CONTRADICTED = "CONTRADICTED"

    # Source-compatible aliases for callers compiled against the original schema.
    EXISTING_TEST = "COVERED"
    MISSING_TEST = "MISSING"
    CONTRADICTED_TEST = "CONTRADICTED"


class AnalysisStatus(StrEnum):
    QUEUED = "QUEUED"
    INGESTING = "INGESTING"
    PARSING = "PARSING"
    INDEXING = "INDEXING"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    RISK_ANALYSIS = "RISK_ANALYSIS"
    TEST_GAP_ANALYSIS = "TEST_GAP_ANALYSIS"
    VERIFICATION = "VERIFICATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SupportStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"
    CONTESTED = "CONTESTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ChangeIntent(StrictModel):
    entities: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    states_added: list[str] = Field(default_factory=list)
    states_removed: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_behaviors: list[str] = Field(default_factory=list)


class SourceLocation(StrictModel):
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    symbol: str | None = None

    @model_validator(mode="after")
    def valid_range(self) -> SourceLocation:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class Evidence(StrictModel):
    id: str
    type: EvidenceType
    repository_snapshot_id: str
    repository_id: str = "unknown"
    commit_sha: str = "unknown"
    location: SourceLocation
    content_hash: str
    reason: str
    strength: EvidenceStrength = EvidenceStrength.DIRECT
    quality_score: float = Field(default=1.0, ge=0, le=1)
    snippet: str = ""
    status: str = "VALID"


class Component(StrictModel):
    id: str
    type: ComponentType
    name: str
    location: SourceLocation
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.DIRECT
    impact_status: ImpactStatus = ImpactStatus.CANDIDATE
    reasoning_path: list[str] = Field(default_factory=list)

    @property
    def stable_key(self) -> str:
        return f"{self.type.value}:{self.location.file}:{self.name}"


class GraphEdge(StrictModel):
    source: str
    target: str
    relationship: str
    evidence_id: str | None = None


class BusinessRule(StrictModel):
    id: str
    statement: str
    classification: RuleClassification
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)
    source_locations: list[SourceLocation] = Field(default_factory=list)
    repository_snapshot_id: str = "unknown"
    status: str = "ACTIVE"


class LineChange(StrictModel):
    old_line: int | None = Field(default=None, ge=1)
    new_line: int | None = Field(default=None, ge=1)
    content: str


class SymbolChange(StrictModel):
    name: str
    component_type: ComponentType
    change_kind: ChangeKind
    before_location: SourceLocation | None = None
    after_location: SourceLocation | None = None


class StateValueChange(StrictModel):
    state_machine: str
    value: str
    change_kind: ChangeKind
    evidence_ids: list[str] = Field(default_factory=list)


class DiffChange(StrictModel):
    old_path: str | None = None
    new_path: str | None = None
    change_kind: ChangeKind
    added_lines: list[LineChange] = Field(default_factory=list)
    deleted_lines: list[LineChange] = Field(default_factory=list)
    modified_lines: list[LineChange] = Field(default_factory=list)
    symbol_changes: list[SymbolChange] = Field(default_factory=list)
    state_changes: list[StateValueChange] = Field(default_factory=list)
    changed_api_routes: list[str] = Field(default_factory=list)
    changed_db_fields: list[str] = Field(default_factory=list)
    changed_sql_references: list[str] = Field(default_factory=list)


class ChangeSet(StrictModel):
    before_snapshot_id: str
    after_snapshot_id: str
    before_commit_sha: str
    after_commit_sha: str
    source: str
    files: list[DiffChange] = Field(default_factory=list)


class GraphDelta(StrictModel):
    added_components: list[str] = Field(default_factory=list)
    removed_components: list[str] = Field(default_factory=list)
    modified_components: list[str] = Field(default_factory=list)
    added_relationships: list[GraphEdge] = Field(default_factory=list)
    removed_relationships: list[GraphEdge] = Field(default_factory=list)


class StateTransition(StrictModel):
    from_state: str
    to_state: str
    handler: str | None = None
    side_effects: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    tests: list[str] = Field(default_factory=list)


class StateMachine(StrictModel):
    id: str
    entity: str
    states: list[str]
    transitions: list[StateTransition]
    repository_snapshot_id: str


class Contradiction(StrictModel):
    id: str
    claim: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=2)
    status: str = "CONTRADICTORY"


class ChangeDecision(StrictModel):
    status: DecisionStatus
    rationale: list[str]
    required_actions: list[str]


class RiskFactors(StrictModel):
    dependency_impact: float = Field(ge=0, le=25)
    business_criticality: float = Field(ge=0, le=25)
    test_gap: float = Field(ge=0, le=20)
    integration_exposure: float = Field(ge=0, le=15)
    ambiguity: float = Field(ge=0, le=10)
    change_distance: float = Field(default=0, ge=0, le=10)
    boundary_count: float = Field(default=0, ge=0, le=5)
    affected_state_transitions: float = Field(default=0, ge=0, le=10)


class Risk(StrictModel):
    risk_id: str
    title: str
    severity: Severity
    risk_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    claim: str
    reasoning: str
    evidence: list[str] = Field(min_length=1)
    affected_components: list[str] = Field(min_length=1)
    recommended_action: str
    factors: RiskFactors
    support_status: SupportStatus = SupportStatus.SUPPORTED
    evidence_strength: EvidenceStrength = EvidenceStrength.UNCERTAIN


class TestScenario(StrictModel):
    scenario_id: str
    priority: Severity
    category: str
    behavior: str
    actor: str
    preconditions: list[str]
    action: str
    expected_result: str
    invariant: list[str]
    related_requirement: str
    related_risk: str | None = None
    evidence: list[str] = Field(min_length=1)
    affected_components: list[str] = Field(min_length=1)
    why_missing: str
    reason_it_matters: str
    coverage: CoverageStatus


class ImpactSummary(StrictModel):
    affected_files: int = 0
    affected_components: int = 0
    business_rules: int = 0
    apis: int = 0
    database_entities: int = 0
    background_jobs: int = 0
    integrations: int = 0
    related_tests: int = 0


class AnalysisResult(StrictModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    repository: str
    commit_sha: str
    snapshot_id: str
    analyzer_version: str
    timestamp: datetime = Field(default_factory=utcnow)
    model_version: str
    semantic_analysis: str = "AVAILABLE"
    change_request: str
    intent: ChangeIntent
    change_set: ChangeSet | None = None
    graph_delta: GraphDelta | None = None
    impact_summary: ImpactSummary
    components: list[Component]
    candidate_components: list[Component] = Field(default_factory=list)
    graph_edges: list[GraphEdge]
    evidence: list[Evidence]
    business_rules: list[BusinessRule]
    state_machines: list[StateMachine] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    risks: list[Risk]
    test_gaps: list[TestScenario]
    change_plan: list[str]
    decision: ChangeDecision
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class RepositoryCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    source_path: str | None = None
    github_url: str | None = None
    default_branch: str = "main"


class ChangeCreate(StrictModel):
    repository_id: UUID
    description: str = Field(min_length=10, max_length=10_000)
    proposed_diff: str | None = Field(default=None, max_length=2_000_000)
    base_ref: str | None = Field(default=None, max_length=200)
    target_ref: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid_comparison(self) -> ChangeCreate:
        if bool(self.base_ref) != bool(self.target_ref):
            raise ValueError("base_ref and target_ref must be provided together")
        if self.proposed_diff and self.base_ref:
            raise ValueError("provide proposed_diff or refs, not both")
        return self


class FindingFeedbackCreate(StrictModel):
    decision: str
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_decision(self) -> FindingFeedbackCreate:
        if self.decision not in {"CONFIRM", "REJECT", "NOT_RELEVANT"}:
            raise ValueError("decision must be CONFIRM, REJECT, or NOT_RELEVANT")
        return self


class JobView(StrictModel):
    id: UUID
    status: AnalysisStatus
    progress: int = Field(ge=0, le=100)
    analysis_id: UUID | None = None
    error: str | None = None
