from __future__ import annotations

import hashlib

from changetrace_schemas import (
    BusinessRule,
    Component,
    ComponentType,
    EvidenceStrength,
    Risk,
    RiskFactors,
    Severity,
    StateMachine,
    SupportStatus,
)

CRITICAL_TERMS = {
    "refund",
    "payment",
    "authorization",
    "permission",
    "warehouse",
    "order",
    "fee",
    "settlement",
    "currency",
}
INTEGRATION_TYPES = {ComponentType.INTEGRATION, ComponentType.API, ComponentType.JOB}


def severity_for(score: int) -> Severity:
    if score >= 75:
        return Severity.CRITICAL
    if score >= 50:
        return Severity.HIGH
    if score >= 25:
        return Severity.MEDIUM
    return Severity.LOW


def normalized_score(factors: RiskFactors) -> int:
    baseline = sum(
        (
            factors.dependency_impact,
            factors.business_criticality,
            factors.test_gap,
            factors.integration_exposure,
            factors.ambiguity,
        )
    )
    # Preserve the documented 95-point baseline. Diff distance, boundary spread, and
    # state-transition exposure are explicit bounded uplifts rather than hidden score changes.
    uplift = factors.change_distance * 0.35 + factors.boundary_count * 0.6 + factors.affected_state_transitions * 0.35
    return min(100, round(baseline / 95 * 100 + uplift))


class RiskEngine:
    def calculate(
        self,
        components: list[Component],
        rules: list[BusinessRule],
        distances: dict[str, int],
        expected_test_gaps: int = 1,
        state_machines: list[StateMachine] | None = None,
        intent: object | None = None,
    ) -> list[Risk]:
        if not components:
            return []
        import re

        evidence = list(dict.fromkeys(eid for component in components for eid in component.evidence_ids))
        boundary_types = {component.type for component in components}
        names = " ".join(component.name.lower() for component in components)
        direct_count = sum(distance == 0 for distance in distances.values())
        dependency = min(25, 4 + direct_count * 2 + max(0, len(boundary_types) - 1) * 1.5)
        criticality = min(25, 5 + sum(4 for term in CRITICAL_TERMS if term in names))
        gap = min(20, 3 + expected_test_gaps * 3)
        exposure = min(15, sum(4 for component in components if component.type in INTEGRATION_TYPES))
        ambiguity = min(10, 2 + len(rules) * 1.5)
        non_direct = [distance for distance in distances.values() if distance > 0]
        change_distance = min(10, sum(non_direct) / max(1, len(non_direct)) * 3)
        boundary_count = min(5, len(boundary_types) * 0.7)
        state_files = {component.location.file for component in components if component.type == ComponentType.STATE}
        transition_count = sum(
            len(machine.transitions)
            for machine in (state_machines or [])
            if any(
                component.location.file in state_files and machine.entity.lower() in component.name.lower()
                for component in components
            )
        )
        affected_transitions = min(10, transition_count * 2)
        factors = RiskFactors(
            dependency_impact=dependency,
            business_criticality=criticality,
            test_gap=gap,
            integration_exposure=exposure,
            ambiguity=ambiguity,
            change_distance=change_distance,
            boundary_count=boundary_count,
            affected_state_transitions=affected_transitions,
        )
        score = normalized_score(factors)
        confidence = min(0.98, 0.45 + min(len(evidence), 8) * 0.05 + min(len(rules), 3) * 0.05)
        central = sorted(components, key=lambda c: (distances.get(c.id, 9), -len(c.evidence_ids)))[:8]
        central_component = central[0]
        all_text = " ".join(f"{c.name} {c.location.file}" for c in central).lower()
        has_state = bool(state_machines or ComponentType.STATE in boundary_types or transition_count > 0 or "state" in names)

        intent_terms = set()
        if intent:
            intent_terms.update(getattr(intent, "entities", []))
            intent_terms.update(getattr(intent, "actions", []))
            intent_terms.update(getattr(intent, "states_added", []))
            for c in getattr(intent, "constraints", []) + getattr(intent, "expected_behaviors", []):
                intent_terms.update(re.findall(r"[a-z0-9_]+", c.lower()))
        intent_terms = {t.lower() for t in intent_terms}

        claim_terms: set[str] = set()
        if "refund" in intent_terms or (not intent and "refund" in names):
            claim = "The proposed refund change may bypass or conflict with current refund eligibility and processing conditions."
            title = "Refund processing change path requires explicit verification"
            claim_terms = {"refund", "eligible", "eligibility", "condition"}
        elif "currency" in intent_terms or "fx" in intent_terms or "settlement" in intent_terms or (not intent and ("currency" in names or "fx" in names)):
            claim = "The proposed currency settlement change affects automated FX conversion, fee calculation, and dependent processing paths."
            title = "Foreign currency and FX settlement change path requires verification"
            claim_terms = {"currency", "fx", "settlement", "fee"}
        elif "fee" in intent_terms or (not intent and "fee" in names):
            claim = "The proposed fee change affects fee service calculation and payment adjustments."
            title = "State transition and fee processing change path requires verification"
            claim_terms = {"fee", "payment", "state", "transition"}
        elif "authorization" in names or "permission" in names or "authorization" in intent_terms or "permission" in intent_terms:
            claim = f"The requested authorization change affects the existing {central_component.name} change path and condition checks."
            title = "Authorization change path requires verification"
            claim_terms = {"authorization", "permission", "access", "condition"}
        elif bool(intent and getattr(intent, "states_added", None)) or bool(intent_terms & {"state", "transition", "pause", "paused"}):
            claim = f"The proposed state transition and status change in {central_component.name} introduces unverified lifecycle paths."
            title = f"State transition and {central_component.name} change path requires verification"
            claim_terms = {"state", "status", "transition", "lifecycle", central_component.name.lower()}
        else:
            claim = "The proposed behavior crosses existing business conditions and dependency boundaries."
            title = "Existing change path may not support the proposed behavior"
            claim_terms = {"business", "condition", "dependency"}

        evidence_by_component = {
            evidence_id: component
            for component in components
            for evidence_id in component.evidence_ids
        }
        compatible_evidence = [
            evidence_id
            for evidence_id in evidence
            if any(
                term
                in (
                    f"{evidence_by_component[evidence_id].name} "
                    f"{evidence_by_component[evidence_id].location.file}"
                ).lower()
                for term in claim_terms
            )
        ]
        if not compatible_evidence:
            claim = f"The requested change affects the existing {central_component.name} change path."
            title = "Existing change path requires verification"
            compatible_evidence = list(central_component.evidence_ids)
        evidence = compatible_evidence
        risk_id = "RISK-" + hashlib.sha1((title + ":".join(evidence)).encode()).hexdigest()[:10]  # noqa: S324
        strengths = [component.evidence_strength for component in central]
        evidence_strength = (
            EvidenceStrength.DIRECT
            if EvidenceStrength.DIRECT in strengths
            else EvidenceStrength.STRONG
            if EvidenceStrength.STRONG in strengths
            else EvidenceStrength.INDIRECT
        )
        return [
            Risk(
                risk_id=risk_id,
                title=title,
                severity=severity_for(score),
                risk_score=score,
                confidence=confidence,
                claim=claim,
                reasoning=(
                    f"Deterministic analysis found {len(components)} affected components across "
                    f"{len(boundary_types)} boundary types and {len(rules)} evidenced business rules."
                ),
                evidence=evidence[:12],
                affected_components=[item.id for item in central],
                recommended_action=(
                    "Review the evidenced conditions, update the transition path, and add focused regression tests."
                ),
                factors=factors,
                support_status=SupportStatus.SUPPORTED,
                evidence_strength=evidence_strength,
            )
        ]


class AdversarialVerifier:
    def review(self, risks: list[Risk], components: list[Component]) -> list[Risk]:
        tests = [component for component in components if component.type == ComponentType.TEST]
        result = []
        for risk in risks:
            matching = [
                test
                for test in tests
                if any(word in test.name.lower() for word in risk.title.lower().split() if len(word) > 5)
            ]
            if matching:
                result.append(
                    risk.model_copy(
                        update={
                            "support_status": SupportStatus.CONTESTED,
                            "confidence": max(0.1, risk.confidence - 0.12),
                            "reasoning": risk.reasoning
                            + " A potentially contradictory existing test was detected and needs inspection.",
                        }
                    )
                )
            elif len(risk.evidence) < 2:
                result.append(
                    risk.model_copy(
                        update={
                            "support_status": SupportStatus.WEAKLY_SUPPORTED,
                            "confidence": min(risk.confidence, 0.45),
                        }
                    )
                )
            else:
                result.append(risk)
        return result
