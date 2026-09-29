from pathlib import Path

from changetrace_schemas import ComponentType

from services.repository_analysis import RepositoryAnalyzer

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_extracts_routes_rules_jobs_databases_and_tests():
    index = RepositoryAnalyzer().scan(FIXTURE, "snap-test", "commit-test")
    types = {component.type for component in index.components}
    assert {
        ComponentType.API,
        ComponentType.BUSINESS_RULE,
        ComponentType.JOB,
        ComponentType.DATABASE,
        ComponentType.TEST,
    } <= types
    assert all(evidence.repository_snapshot_id == "snap-test" for evidence in index.evidence)
