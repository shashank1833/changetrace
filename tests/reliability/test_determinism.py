from pathlib import Path

from workers.analysis import AnalysisPipeline

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"
REQUEST = "Handle payment provider timeout while reversing an order payment."


def stable_projection(result):
    return {
        "snapshot": result.snapshot_id,
        "commit": result.commit_sha,
        "components": [(item.stable_key, item.impact_status.value) for item in result.components],
        "evidence": [(item.id, item.content_hash) for item in result.evidence],
        "risks": [(item.risk_id, item.risk_score, item.severity.value) for item in result.risks],
        "test_gaps": [(item.scenario_id, item.coverage.value) for item in result.test_gaps],
        "decision": result.decision.status.value,
    }


def test_same_snapshot_and_request_have_stable_analysis():
    first = AnalysisPipeline().run(FIXTURE, REQUEST)
    second = AnalysisPipeline().run(FIXTURE, REQUEST)
    assert stable_projection(first) == stable_projection(second)
