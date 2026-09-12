from __future__ import annotations

from changetrace_schemas import ChangeDecision, DecisionStatus, Severity, SupportStatus


class DecisionEngine:
    """Apply explicit release policy to verified findings; no model chooses the decision."""

    def decide(self, risks, test_gaps, contradictions, change_plan: list[str]) -> ChangeDecision:
        trusted = [
            risk
            for risk in risks
            if risk.evidence
            and risk.affected_components
            and risk.evidence_strength not in {"SEMANTIC", "UNCERTAIN"}
            and risk.support_status == SupportStatus.SUPPORTED
        ]
        supported_critical = [
            risk for risk in trusted if risk.severity == Severity.CRITICAL and risk.confidence >= 0.75
        ]
        high_confidence = [
            risk for risk in trusted if risk.severity in {Severity.HIGH, Severity.CRITICAL} and risk.confidence >= 0.65
        ]
        critical_gaps = [
            gap
            for gap in test_gaps
            if gap.priority == Severity.CRITICAL and gap.coverage.value in {"MISSING", "UNCERTAIN", "PARTIALLY_COVERED"}
        ]
        if supported_critical and critical_gaps:
            status = DecisionStatus.BLOCK
        elif high_confidence or critical_gaps or contradictions:
            status = DecisionStatus.REVIEW
        else:
            status = DecisionStatus.GO
        rationale = []
        if high_confidence:
            evidence_count = len({evidence_id for risk in high_confidence for evidence_id in risk.evidence})
            rationale.append(
                f"{len(high_confidence)} high-confidence high/critical risk(s) supported by "
                f"{evidence_count} evidence reference(s)"
            )
        if critical_gaps:
            rationale.append(f"{len(critical_gaps)} critical verification scenario(s) are not covered")
        if contradictions:
            rationale.append(f"{len(contradictions)} documentation/implementation contradiction(s)")
        if not rationale:
            rationale.append("No verified policy threshold requires review")
        return ChangeDecision(status=status, rationale=rationale, required_actions=change_plan[:6])
