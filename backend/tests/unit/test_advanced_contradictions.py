from pathlib import Path

from services.business_rules import ContradictionDetector
from services.evidence import EvidenceEngine
from services.repository_analysis import RepositoryAnalyzer


def test_code_vs_code_contradiction_detected(tmp_path: Path):
    # Service A enforces a refund restriction
    (tmp_path / "order_guard.py").write_text(
        """def validate_refund(order):
    if order.status == "SHIPPED":
        raise ValueError("Shipped orders cannot be refunded without inspection")
    return True
"""
    )
    # Service B processes refund directly
    (tmp_path / "refund_route.py").write_text(
        """def direct_refund(order):
    # Shipped orders refunded directly
    order.status = "REFUNDED"
    return order
"""
    )
    index = RepositoryAnalyzer().scan(tmp_path, "snap-contra", "commit-contra")
    evidence = EvidenceEngine().collect(index, index.components)
    detector = ContradictionDetector()
    contradictions = detector.detect(index.components, evidence)

    assert len(contradictions) >= 1
    assert any("Conflicting business logic" in c.claim for c in contradictions)
    assert all(len(c.evidence_ids) >= 2 for c in contradictions)


def test_test_vs_code_contradiction_detected(tmp_path: Path):
    # Test asserts cancel is rejected/forbidden
    (tmp_path / "test_subscriptions.py").write_text(
        """def test_cannot_cancel_active():
    with pytest.raises(ForbiddenError):
        cancel_subscription()
"""
    )
    # Implementation cancels directly without checks
    (tmp_path / "subscriptions.py").write_text(
        """def cancel_subscription():
    sub.status = "CANCELLED"
    return sub
"""
    )
    index = RepositoryAnalyzer().scan(tmp_path, "snap-contra2", "commit-contra2")
    evidence = EvidenceEngine().collect(index, index.components)
    detector = ContradictionDetector()
    contradictions = detector.detect(index.components, evidence)

    assert len(contradictions) >= 1
    assert any("expects rejection" in c.claim for c in contradictions)
