from changetrace_schemas import (
    CoverageStatus,
    EvidenceStrength,
    Risk,
    RiskFactors,
    Severity,
    SupportStatus,
)
from changetrace_schemas import (
    TestScenario as Scenario,
)

from services.decisions import DecisionEngine

FACTORS = RiskFactors(
    dependency_impact=10,
    business_criticality=10,
    test_gap=10,
    integration_exposure=5,
    ambiguity=2,
)


def risk(severity: Severity, confidence: float) -> Risk:
    return Risk(
        risk_id="risk",
        title="risk",
        severity=severity,
        risk_score=80 if severity == Severity.CRITICAL else 55,
        confidence=confidence,
        claim="claim",
        reasoning="reason",
        evidence=["evidence"],
        affected_components=["component"],
        recommended_action="review",
        factors=FACTORS,
        support_status=SupportStatus.SUPPORTED,
        evidence_strength=EvidenceStrength.DIRECT,
    )


def gap(coverage: CoverageStatus) -> Scenario:
    return Scenario(
        scenario_id="gap",
        priority=Severity.CRITICAL,
        category="state transition",
        behavior="verify transition",
        actor="actor",
        preconditions=["precondition"],
        action="act",
        expected_result="result",
        invariant=["invariant"],
        related_requirement="requirement",
        evidence=["evidence"],
        affected_components=["component"],
        why_missing="reason",
        reason_it_matters="protect invariant",
        coverage=coverage,
    )


def decide(risks, gaps):
    return DecisionEngine().decide(risks, gaps, [], [])


def test_critical_high_confidence_risk_and_missing_critical_test_blocks():
    assert decide([risk(Severity.CRITICAL, 0.9)], [gap(CoverageStatus.MISSING_TEST)]).status.value == "BLOCK"


def test_high_impact_low_confidence_requires_review_not_block():
    assert decide([risk(Severity.CRITICAL, 0.4)], []).status.value == "GO"


def test_unsupported_or_semantic_risk_cannot_block():
    unsupported = risk(Severity.CRITICAL, 0.9).model_copy(
        update={"support_status": SupportStatus.INSUFFICIENT_EVIDENCE}
    )
    semantic = risk(Severity.CRITICAL, 0.9).model_copy(update={"evidence_strength": EvidenceStrength.SEMANTIC})

    assert decide([unsupported], [gap(CoverageStatus.MISSING)]).status.value == "REVIEW"
    assert decide([semantic], [gap(CoverageStatus.MISSING)]).status.value == "REVIEW"


def test_block_rationale_reports_supporting_evidence_count():
    decision = decide([risk(Severity.CRITICAL, 0.9)], [gap(CoverageStatus.MISSING)])

    assert decision.status.value == "BLOCK"
    assert any("evidence reference" in reason for reason in decision.rationale)


def test_uncertain_critical_coverage_is_not_treated_as_existing():
    assert decide([], [gap(CoverageStatus.UNCERTAIN)]).status.value == "REVIEW"
