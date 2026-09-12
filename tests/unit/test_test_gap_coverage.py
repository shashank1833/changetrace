from pathlib import Path

from changetrace_schemas import ComponentType, CoverageStatus

from services.changes import ChangeInterpreter
from services.repository_analysis import RepositoryAnalyzer
from services.test_gaps import TestGapEngine


def generate(tmp_path: Path, test_source: str):
    (tmp_path / "service.py").write_text("def refund_order(order):\n    return order.status == 'PAID'\n")
    (tmp_path / "test_service.py").write_text(test_source)
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    components = [item for item in index.components if item.type != ComponentType.FILE]
    intent = ChangeInterpreter().interpret("Add a paid order refund and reject invalid refunds")
    return TestGapEngine().generate(intent, components, None, index)


def test_assertions_and_called_symbols_can_establish_existing_coverage(tmp_path: Path):
    scenarios = generate(
        tmp_path,
        "from service import refund_order\n\n"
        "def test_refund_rules():\n"
        "    assert refund_order(type('O', (), {'status': 'PAID'})())\n",
    )
    happy = next(item for item in scenarios if item.category == "happy path")
    assert happy.coverage == CoverageStatus.EXISTING_TEST


def test_parameterized_equivalent_state_transition_coverage_is_detected(tmp_path: Path):
    scenarios = generate(
        tmp_path,
        "import pytest\nfrom service import refund_order\n\n"
        "@pytest.mark.parametrize('status, expected', [('PAID', True), ('NEW', False)])\n"
        "def test_refund_states(status, expected):\n"
        "    assert refund_order(type('O', (), {'status': status})()) is expected\n",
    )
    happy = next(item for item in scenarios if item.category == "happy path")

    assert happy.coverage == CoverageStatus.COVERED


def test_uncertain_coverage_is_not_reported_as_missing(tmp_path: Path):
    scenarios = generate(tmp_path, "def test_math():\n    assert 1 + 1 == 2\n")
    authorization = next(item for item in scenarios if item.category == "negative path")

    assert authorization.coverage == CoverageStatus.UNCERTAIN
    assert authorization.coverage != CoverageStatus.MISSING


def test_unrelated_test_does_not_remove_gap(tmp_path: Path):
    scenarios = generate(tmp_path, "def test_math():\n    assert 1 + 1 == 2\n")
    happy = next(item for item in scenarios if item.category == "happy path")
    assert happy.coverage != CoverageStatus.EXISTING_TEST
