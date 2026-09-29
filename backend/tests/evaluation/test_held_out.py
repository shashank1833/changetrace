from __future__ import annotations

from tests.evaluation.held_out.run import evaluate


def test_held_out_production_accuracy():
    metrics = evaluate()
    assert metrics["scenarios"] >= 3
    assert metrics["impact_precision"] >= 0.25, f"Impact precision {metrics['impact_precision']} below minimum"
    assert metrics["evidence_validity_rate"] == 1.0, "All evidence must be valid"
    assert metrics["unsupported_claim_rate"] == 0.0, "No unsupported claims permitted"
    assert metrics["false_positive_rate"] == 0.0, "No known false positives should be identified as confirmed"
    assert metrics["median_analysis_seconds"] < 1.0, "Analysis must execute in sub-second duration"
