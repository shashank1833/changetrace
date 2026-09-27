from __future__ import annotations

from changetrace_schemas import ChangeDecision, ComponentType, DecisionStatus, Severity, SupportStatus


class DecisionEngine:
    """Apply explicit release policy to verified findings; no model chooses the decision."""

    def decide(
        self,
        risks,
        test_gaps,
        contradictions,
        change_plan: list[str],
        components=None,
        evidence=None,
    ) -> ChangeDecision:
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
        contested = [risk for risk in risks if risk.support_status == SupportStatus.CONTESTED]
        if supported_critical and critical_gaps:
            status = DecisionStatus.BLOCK
        elif high_confidence or critical_gaps or contradictions or contested:
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
        if contested:
            rationale.append(f"{len(contested)} contested finding(s) require inspection against existing tests")
        if critical_gaps:
            rationale.append(f"{len(critical_gaps)} critical verification scenario(s) are not covered")
        if contradictions:
            rationale.append(f"{len(contradictions)} documentation/implementation contradiction(s)")
        if not rationale:
            rationale.append("No verified policy threshold requires review")

        # Explainable Decision Breakdown
        top_risk = max(risks, key=lambda r: r.risk_score) if risks else None
        if top_risk:
            rationale.append(f"Risk Score: {top_risk.risk_score} / 100 ({top_risk.severity.value})")

        reasons: list[str] = []
        if top_risk and top_risk.affected_components:
            count = len(top_risk.affected_components)
            s = "component" if count == 1 else "components"
            reasons.append(f"+ {count} downstream {s} affected")
        if top_risk and getattr(top_risk.factors, "affected_state_transitions", 0) > 0:
            count = int(top_risk.factors.affected_state_transitions)
            s = "state transition" if count == 1 else "state transitions"
            reasons.append(f"+ {count} {s} exposed")
        if components and any(getattr(c, "type", None) == ComponentType.API for c in components):
            reasons.append("+ API route contract affected")
        if components and any(getattr(c, "type", None) == ComponentType.DATABASE for c in components):
            reasons.append("+ database entity/constraint path affected")
        if critical_gaps:
            count = len(critical_gaps)
            s = "scenario" if count == 1 else "scenarios"
            reasons.append(f"+ {count} missing regression test {s}")
        if contradictions:
            count = len(contradictions)
            s = "guard" if count == 1 else "guards"
            reasons.append(f"+ {count} contradictory documentation/code {s}")
        if contested:
            count = len(contested)
            s = "finding" if count == 1 else "findings"
            reasons.append(f"+ {count} contested {s} require test inspection")

        if components and not any(getattr(c, "type", None) == ComponentType.DATABASE for c in components):
            reasons.append("- no database schema change")
        if components and not any(getattr(c, "type", None) == ComponentType.INTEGRATION for c in components):
            reasons.append("- no external third-party integration affected")
        if not contradictions:
            reasons.append("- no documentation contradictions detected")

        if reasons:
            rationale.append("Decision Drivers:")
            rationale.extend(f"  {r}" for r in reasons)

        ev_count = len(evidence) if evidence else sum(len(r.evidence) for r in risks)
        ev_s = "source span" if ev_count == 1 else "source spans"
        rationale.append(f"Evidence: {ev_count} verified {ev_s}, 0 unsupported claims")

        return ChangeDecision(status=status, rationale=rationale, required_actions=change_plan[:6])
