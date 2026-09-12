from __future__ import annotations

from changetrace_schemas import AnalysisResult

from services.evidence import EvidenceEngine
from services.repository_analysis import IndexedRepository
from services.risks import normalized_score, severity_for


class VerificationError(ValueError):
    pass


class ResultVerifier:
    def verify(self, result: AnalysisResult, index: IndexedRepository) -> AnalysisResult:
        evidence_by_id = {item.id: item for item in result.evidence}
        component_ids = {item.id for item in result.components}
        engine = EvidenceEngine()
        invalid = [item.id for item in result.evidence if not engine.validate(item, index)]
        if invalid:
            raise VerificationError(f"Invalid or stale evidence: {invalid}")
        wrong_snapshot = [
            item.id
            for item in result.evidence
            if item.repository_snapshot_id != result.snapshot_id
            or item.commit_sha != result.commit_sha
            or item.repository_id != index.repository_id
        ]
        if wrong_snapshot:
            raise VerificationError(f"Evidence belongs to another snapshot: {wrong_snapshot}")
        for rule in result.business_rules:
            self._require_evidence(rule.evidence_ids, evidence_by_id, f"rule {rule.id}")
        for risk in result.risks:
            self._require_evidence(risk.evidence, evidence_by_id, f"risk {risk.risk_id}")
            compatible = [
                evidence_id
                for evidence_id in risk.evidence
                if engine.supports_claim(evidence_by_id[evidence_id], risk.claim)
            ]
            if not compatible:
                raise VerificationError(f"Risk {risk.risk_id} has no claim-compatible evidence")
            if not set(risk.affected_components) <= component_ids:
                raise VerificationError(f"Risk {risk.risk_id} references an unknown component")
            expected = normalized_score(risk.factors)
            if risk.risk_score != expected or risk.severity != severity_for(expected):
                raise VerificationError(f"Risk {risk.risk_id} score is not reproducible")
        for scenario in result.test_gaps:
            self._require_evidence(scenario.evidence, evidence_by_id, f"scenario {scenario.scenario_id}")
            if not set(scenario.affected_components) <= component_ids:
                raise VerificationError(f"Scenario {scenario.scenario_id} references an unknown component")
        for contradiction in result.contradictions:
            self._require_evidence(
                contradiction.evidence_ids,
                evidence_by_id,
                f"contradiction {contradiction.id}",
            )
        if len({risk.risk_id for risk in result.risks}) != len(result.risks):
            raise VerificationError("Duplicate risks are not allowed")
        if len({scenario.scenario_id for scenario in result.test_gaps}) != len(result.test_gaps):
            raise VerificationError("Duplicate test scenarios are not allowed")
        return result

    @staticmethod
    def _require_evidence(ids, evidence_by_id, subject: str) -> None:
        missing = set(ids) - evidence_by_id.keys()
        if missing:
            raise VerificationError(f"{subject} references nonexistent evidence: {sorted(missing)}")
