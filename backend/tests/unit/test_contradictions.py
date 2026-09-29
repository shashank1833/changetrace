from pathlib import Path

from services.business_rules import ContradictionDetector
from services.changes import ChangeInterpreter
from services.evidence import EvidenceEngine
from services.graph import RepositoryGraph
from services.impact import ImpactEngine
from services.repository_analysis import RepositoryAnalyzer

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_documented_final_shipment_conflicts_with_return_path():
    index = RepositoryAnalyzer().scan(FIXTURE, "snap-contradiction", "commit-contradiction")
    intent = ChangeInterpreter().interpret("Permit refunds for shipped orders after warehouse inspection.")
    components, _rules, _distances = ImpactEngine().discover(index, RepositoryGraph(index), intent)
    evidence = EvidenceEngine().collect(index, components)
    contradictions = ContradictionDetector().detect(components, evidence)
    assert contradictions
    ids = {item.id for item in evidence}
    assert all(set(item.evidence_ids) <= ids for item in contradictions)
