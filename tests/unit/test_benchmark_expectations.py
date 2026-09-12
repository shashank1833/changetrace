from changetrace_schemas import Component, ComponentType, EvidenceStrength, ImpactStatus, SourceLocation

from tests.evaluation.benchmark.run import matches_expected_finding


def finding(status: ImpactStatus = ImpactStatus.LIKELY) -> Component:
    return Component(
        id="C-1",
        type=ComponentType.FUNCTION,
        name="process_refund",
        location=SourceLocation(file="refund.py", line_start=4, line_end=8, symbol="process_refund"),
        reason="direct call",
        evidence_ids=["E-1"],
        evidence_strength=EvidenceStrength.STRONG,
        impact_status=status,
        reasoning_path=["RELATIONSHIP CALLS reverse_payment"],
    )


def test_symbol_level_expectation_does_not_accept_an_unrelated_symbol_in_same_file():
    expectation = {"file": "refund.py", "symbol": "refund_is_eligible", "classification": "LIKELY"}

    assert not matches_expected_finding(finding(), expectation)


def test_structural_expectation_checks_relationship_and_classification():
    expectation = {
        "file": "refund.py",
        "symbol": "process_refund",
        "component_type": "FUNCTION",
        "relationship": "CALLS reverse_payment",
        "classification": "LIKELY",
    }

    assert matches_expected_finding(finding(), expectation)
    assert not matches_expected_finding(finding(ImpactStatus.CANDIDATE), expectation)
