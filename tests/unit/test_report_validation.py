import json
from pathlib import Path

from changetrace_schemas import AnalysisResult

from services.reporting import ReportExporter
from workers.analysis import AnalysisPipeline

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_json_and_markdown_exports_preserve_provenance_and_references():
    result = AnalysisPipeline().run(FIXTURE, "Handle payment provider timeout while reversing an order payment.")
    exported = json.loads(ReportExporter.json(result))
    validated = AnalysisResult.model_validate(exported)
    evidence_ids = {item.id for item in validated.evidence}
    assert validated.snapshot_id == result.snapshot_id
    assert all(set(risk.evidence) <= evidence_ids for risk in validated.risks)
    markdown = ReportExporter.markdown(result)
    assert result.snapshot_id in markdown
    assert result.commit_sha in markdown
    assert result.decision.status.value in markdown
