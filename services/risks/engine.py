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

CRITICAL_TERMS = {"refund", "payment", "authorization", "permission", "warehouse", "order"}
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
    ) -> list[Risk]:
        if not components:
            return []
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
        claim = "The proposed behavior crosses existing business conditions and dependency boundaries."
        title = "Existing change path may not support the proposed behavior"
        claim_terms = {"business", "condition", "dependency"}
        if "refund" in names:
            claim = "The proposed state change may bypass or conflict with current refund eligibility processing."
            title = "Refund processing change path requires explicit verification"
            claim_terms = {"refund", "eligible", "eligibility"}
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
            # Use a precise claim that the selected component evidence can support
            # instead of attaching unrelated provenance to a generic risk statement.
            central_component = sorted(components, key=lambda c: (distances.get(c.id, 9), -len(c.evidence_ids)))[0]
            claim = f"The requested change affects the existing {central_component.name} change path."
            title = "Existing change path requires verification"
            if "authorization" in names or "permission" in names:
                claim = f"The requested authorization change affects the existing {central_component.name} change path."
                title = "Authorization change path requires verification"
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
