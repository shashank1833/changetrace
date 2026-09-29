import json
from pathlib import Path

import pytest

from workers.analysis import AnalysisPipeline

HERE = Path(__file__).parent
BENCHMARK = HERE / "benchmark"


@pytest.mark.evaluation
def test_known_impact_recall_is_measured_not_fabricated():
    expected = json.loads((HERE / "expected_impacts.json").read_text())
    result = AnalysisPipeline().run(HERE / "demo_repository", expected["request"])
    found = {component.location.file for component in result.components}
    required = set(expected["must_find_files"])
    recall = len(found & required) / len(required)
    assert recall >= 0.70, {"recall": recall, "missing": sorted(required - found)}
    categories = {scenario.category for scenario in result.test_gaps if scenario.coverage.value == "MISSING"}
    assert set(expected["known_missing_categories"]) <= categories


@pytest.mark.evaluation
def test_expanded_benchmark_defines_required_categories():
    scenarios = json.loads((BENCHMARK / "scenarios.json").read_text())
    assert 30 <= len(scenarios) <= 50
    required = {
        "direct dependency",
        "indirect dependency",
        "business rule dependency",
        "database dependency",
        "background job dependency",
        "integration dependency",
        "authorization impact",
        "state transition impact",
        "contradictory documentation",
        "false dependency",
        "dead code",
        "ambiguous naming",
        "semantic-only relationship",
        "cross-module dependency",
        "hidden business logic",
        "idempotency issue",
        "rollback behavior",
        "data consistency issue",
        "API contract impact",
    }
    assert required <= {scenario["category"] for scenario in scenarios}
    for scenario in scenarios:
        assert {
            "change_request",
            "expected_affected_components",
            "expected_business_rules",
            "expected_important_evidence",
            "expected_risks",
            "expected_test_gaps",
            "known_false_positives",
        } <= scenario.keys()
