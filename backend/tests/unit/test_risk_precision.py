from changetrace_schemas import Component, ComponentType, EvidenceStrength, ImpactStatus, SourceLocation

from services.risks import RiskEngine


def component(number: int, kind: ComponentType = ComponentType.FUNCTION) -> Component:
    return Component(
        id=f"C-{number}",
        type=kind,
        name=f"helper_{number}",
        location=SourceLocation(file=f"f{number}.py", line_start=1, line_end=1, symbol=f"helper_{number}"),
        reason="test",
        evidence_ids=[f"E-{number}"],
        evidence_strength=EvidenceStrength.INDIRECT,
        impact_status=ImpactStatus.LIKELY,
    )


def test_irrelevant_breadth_does_not_make_risk_critical():
    components = [component(number) for number in range(40)]
    distances = {item.id: 2 for item in components}
    risk = RiskEngine().calculate(components, [], distances, expected_test_gaps=0)[0]
    assert risk.severity.value != "CRITICAL"
    assert risk.factors.dependency_impact < 15


def test_direct_critical_boundary_scores_higher_than_indirect_helpers():
    helpers = [component(number) for number in range(10)]
    helper_risk = RiskEngine().calculate(helpers, [], {item.id: 2 for item in helpers}, 0)[0]
    payment = component(99, ComponentType.INTEGRATION).model_copy(update={"name": "refund_payment"})
    direct_risk = RiskEngine().calculate([payment], [], {payment.id: 0}, 3)[0]
    assert direct_risk.factors.business_criticality > helper_risk.factors.business_criticality
    assert direct_risk.factors.integration_exposure > helper_risk.factors.integration_exposure
