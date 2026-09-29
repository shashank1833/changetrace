from changetrace_schemas import RiskFactors, Severity

from services.risks import normalized_score, severity_for


def test_risk_score_is_normalized_and_classified():
    factors = RiskFactors(
        dependency_impact=18, business_criticality=22, test_gap=17, integration_exposure=12, ambiguity=6
    )
    score = normalized_score(factors)
    assert score == 79
    assert severity_for(score) == Severity.CRITICAL


def test_risk_boundaries():
    assert severity_for(24) == Severity.LOW
    assert severity_for(25) == Severity.MEDIUM
    assert severity_for(50) == Severity.HIGH
    assert severity_for(75) == Severity.CRITICAL
