from __future__ import annotations

from services.feedback.calibration import FeedbackCalibrationEngine


def test_empty_feedback_calibration():
    engine = FeedbackCalibrationEngine()
    profile = engine.calibrate([])
    assert profile.total_feedback == 0
    assert profile.overall_precision == 1.0
    assert len(profile.categories) == 0


def test_feedback_calibration_high_precision():
    engine = FeedbackCalibrationEngine(min_samples_for_calibration=2)
    records = [
        {"finding_kind": "RISK", "decision": "ACCEPTED"},
        {"finding_kind": "RISK", "decision": "ACCEPTED"},
        {"finding_kind": "RISK", "decision": "ACCEPTED"},
        {"finding_kind": "RISK", "decision": "REJECTED", "reason": "Edge case only"},
    ]
    profile = engine.calibrate(records)
    assert profile.total_feedback == 4
    assert profile.overall_precision == 0.75
    cat = profile.categories["RISK"]
    assert cat.precision == 0.75
    # 0.75 < 0.80 -> mild damping
    assert cat.confidence_multiplier < 1.0
    assert cat.threshold_penalty > 0
    assert "Edge case only" in profile.rejection_reasons


def test_feedback_calibration_low_precision_damping():
    engine = FeedbackCalibrationEngine(min_samples_for_calibration=2)
    records = [
        {"finding_kind": "TEST_GAP", "decision": "ACCEPTED"},
        {"finding_kind": "TEST_GAP", "decision": "REJECTED", "reason": "Already covered elsewhere"},
        {"finding_kind": "TEST_GAP", "decision": "REJECTED", "reason": "Irrelevant component"},
        {"finding_kind": "TEST_GAP", "decision": "REJECTED", "reason": "Already covered elsewhere"},
    ]
    profile = engine.calibrate(records)
    cat = profile.categories["TEST_GAP"]
    assert cat.precision == 0.25
    assert cat.confidence_multiplier <= 0.6  # dampened
    assert cat.threshold_penalty >= 0.1
    assert profile.rejection_reasons["Already covered elsewhere"] == 2
    assert profile.rejection_reasons["Irrelevant component"] == 1


def test_insufficient_samples_preserves_baseline():
    engine = FeedbackCalibrationEngine(min_samples_for_calibration=5)
    records = [
        {"finding_kind": "CONTRADICTION", "decision": "REJECTED"},
    ]
    profile = engine.calibrate(records)
    cat = profile.categories["CONTRADICTION"]
    assert cat.confidence_multiplier == 1.0
    assert cat.threshold_penalty == 0.0
    assert "Insufficient sample size" in cat.rule_explanation
