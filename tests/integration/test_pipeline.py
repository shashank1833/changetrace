from pathlib import Path

from changetrace_schemas import CoverageStatus

from workers.analysis import AnalysisPipeline

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"
REQUEST = (
    "Add RETURNED as a new order state that can occur after shipment and allow refunds "
    "after successful warehouse inspection."
)


def test_pipeline_produces_verified_evidence_linked_result():
    result = AnalysisPipeline().run(FIXTURE, REQUEST)
    evidence_ids = {item.id for item in result.evidence}
    assert result.intent.states_added == ["RETURNED"]
    assert result.impact_summary.affected_components > 0
    assert result.risks and set(result.risks[0].evidence) <= evidence_ids
    assert all(set(gap.evidence) <= evidence_ids for gap in result.test_gaps)
    assert any(gap.coverage == CoverageStatus.MISSING_TEST for gap in result.test_gaps)
    assert result.change_plan
