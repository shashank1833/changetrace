from pathlib import Path

from services.business_rules import ContradictionDetector
from services.evidence import EvidenceEngine
from services.repository_analysis import RepositoryAnalyzer


def indexed_components(tmp_path: Path):
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    return index, index.components, EvidenceEngine().collect(index, index.components)


def test_similar_wording_without_behavioral_opposition_is_not_contradiction(tmp_path: Path):
    (tmp_path / "rules.md").write_text("Refund reports cannot omit an audit identifier.\n")
    (tmp_path / "service.py").write_text("def refund_report(order):\n    return {'audit_id': order.id}\n")
    _, components, evidence = indexed_components(tmp_path)
    assert ContradictionDetector().detect(components, evidence) == []


def test_documented_prohibition_and_allowed_code_path_is_contradiction(tmp_path: Path):
    (tmp_path / "rules.md").write_text("Shipped orders cannot be refunded after shipment.\n")
    (tmp_path / "service.py").write_text(
        "def refund_shipped_order(order):\n"
        "    if order.status == 'SHIPPED':\n"
        "        return refund(order)\n"
    )
    _, components, evidence = indexed_components(tmp_path)
    contradictions = ContradictionDetector().detect(components, evidence)
    assert contradictions
    assert all(len(item.evidence_ids) >= 2 for item in contradictions)
