from pathlib import Path

from changetrace_schemas import Component, ComponentType, Evidence, EvidenceStrength, EvidenceType, SourceLocation

from services.evidence import EvidenceEngine
from services.repository_analysis import RepositoryAnalyzer


def test_direct_source_evidence_scores_above_indirect():
    evidence = Evidence(
        id="E-1",
        type=EvidenceType.CODE_REFERENCE,
        repository_snapshot_id="snap",
        repository_id="repo",
        commit_sha="sha",
        location=SourceLocation(file="a.py", line_start=1, line_end=1, symbol="run"),
        content_hash="hash",
        reason="test",
        snippet="def run(): pass",
    )
    assert EvidenceEngine.quality_score(evidence, EvidenceStrength.DIRECT) > EvidenceEngine.quality_score(
        evidence, EvidenceStrength.INDIRECT
    )


def test_unsupported_evidence_does_not_support_unrelated_claim():
    evidence = Evidence(
        id="E-1",
        type=EvidenceType.CODE_REFERENCE,
        repository_snapshot_id="snap",
        repository_id="repo",
        commit_sha="sha",
        location=SourceLocation(file="notifications.py", line_start=1, line_end=1, symbol="notify_customer"),
        content_hash="hash",
        reason="test",
        snippet="def notify_customer(order): return order.customer_id",
    )

    assert not EvidenceEngine.supports_claim(evidence, "Refund eligibility may charge a payment twice")


def test_claim_compatible_evidence_must_belong_to_the_claimed_symbol():
    evidence = Evidence(
        id="E-refund",
        type=EvidenceType.CODE_REFERENCE,
        repository_snapshot_id="snap",
        repository_id="repo",
        commit_sha="sha",
        location=SourceLocation(file="refund.py", line_start=1, line_end=1, symbol="refund_order"),
        content_hash="hash",
        reason="test",
        snippet="def refund_order(order): return order",
    )
    other = Component(
        id="C-other",
        type=ComponentType.FUNCTION,
        name="refund_report",
        location=SourceLocation(file="reports.py", line_start=1, line_end=1, symbol="refund_report"),
        reason="test",
        evidence_ids=["E-report"],
    )

    assert not EvidenceEngine.supports_component_claim(evidence, "refund order", other)


def test_invalid_repository_identity_rejects_otherwise_valid_reference(tmp_path: Path):
    (tmp_path / "service.py").write_text("def refund_order():\n    return True\n")
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit", "repo-a")
    evidence = index.evidence[1].model_copy(update={"repository_id": "repo-b"})

    assert not EvidenceEngine().validate(evidence, index)
