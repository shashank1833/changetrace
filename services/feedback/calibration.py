from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CategoryCalibration:
    category: str
    sample_count: int
    accepted_count: int
    rejected_count: int
    precision: float
    confidence_multiplier: float
    threshold_penalty: float
    rule_explanation: str


@dataclass
class CalibrationProfile:
    total_feedback: int
    overall_precision: float
    categories: dict[str, CategoryCalibration] = field(default_factory=dict)
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    def get_confidence_multiplier(self, category: str) -> float:
        if category in self.categories:
            return self.categories[category].confidence_multiplier
        return 1.0

    def get_threshold_penalty(self, category: str) -> float:
        if category in self.categories:
            return self.categories[category].threshold_penalty
        return 0.0


class FeedbackCalibrationEngine:
    """Computes deterministic, auditable calibration profiles from user feedback.

    Crucially, this performs empirical rule calibration WITHOUT unverified model retraining.
    All parameter adjustments are mathematically bounded and human-explainable.
    """

    def __init__(self, min_samples_for_calibration: int = 2) -> None:
        self.min_samples = min_samples_for_calibration

    def calibrate(self, feedback_records: list[dict[str, Any]]) -> CalibrationProfile:
        total = len(feedback_records)
        if total == 0:
            return CalibrationProfile(total_feedback=0, overall_precision=1.0)

        accepted_total = sum(1 for f in feedback_records if f.get("decision") == "ACCEPTED")
        rejected_total = sum(1 for f in feedback_records if f.get("decision") == "REJECTED")
        valid_reviews = accepted_total + rejected_total
        overall_precision = accepted_total / valid_reviews if valid_reviews > 0 else 1.0

        # Group by category (e.g. RISK, TEST_GAP, CONTRADICTION or custom category tag)
        grouped: dict[str, list[dict[str, Any]]] = {}
        rejection_reasons: dict[str, int] = {}

        for item in feedback_records:
            cat = item.get("finding_kind") or item.get("category") or "GENERAL"
            grouped.setdefault(cat, []).append(item)

            if item.get("decision") == "REJECTED" and item.get("reason"):
                reason = item["reason"].strip()
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

        calibrations: dict[str, CategoryCalibration] = {}
        for cat, items in grouped.items():
            acc = sum(1 for i in items if i.get("decision") == "ACCEPTED")
            rej = sum(1 for i in items if i.get("decision") == "REJECTED")
            count = acc + rej
            if count == 0:
                continue

            prec = acc / count
            if count >= self.min_samples:
                # If precision is lower than target (0.80), dampen confidence proportionally
                if prec < 0.80:
                    multiplier = max(0.5, round(prec / 0.80, 3))
                    penalty = round((0.80 - prec) * 0.25, 3)
                    explanation = (
                        f"Low acceptance rate ({prec:.1%}, n={count}); "
                        f"damping confidence by {multiplier}x and increasing threshold by {penalty:.3f}"
                    )
                else:
                    multiplier = 1.0
                    penalty = 0.0
                    explanation = f"High acceptance rate ({prec:.1%}, n={count}); full confidence preserved"
            else:
                multiplier = 1.0
                penalty = 0.0
                explanation = f"Insufficient sample size (n={count} < {self.min_samples}); baseline preserved"

            calibrations[cat] = CategoryCalibration(
                category=cat,
                sample_count=count,
                accepted_count=acc,
                rejected_count=rej,
                precision=round(prec, 4),
                confidence_multiplier=multiplier,
                threshold_penalty=penalty,
                rule_explanation=explanation,
            )

        return CalibrationProfile(
            total_feedback=total,
            overall_precision=round(overall_precision, 4),
            categories=calibrations,
            rejection_reasons=rejection_reasons,
        )
