from __future__ import annotations

from changetrace_schemas import Component, Evidence, EvidenceStrength

from services.graph import RepositoryGraph
from services.repository_analysis import IndexedRepository


class EvidenceEngine:
    def collect(self, index: IndexedRepository, components: list[Component]) -> list[Evidence]:
        strengths = {
            evidence_id: component.evidence_strength
            for component in components
            for evidence_id in component.evidence_ids
        }
        selected = set(strengths)
        result = []
        for evidence in index.evidence:
            if evidence.id not in selected:
                continue
            valid = self.validate(evidence, index)
            result.append(
                evidence.model_copy(
                    update={
                        "strength": strengths[evidence.id],
                        "quality_score": self.quality_score(evidence, strengths[evidence.id]) if valid else 0.0,
                        "status": "VALID" if valid else "INVALID",
                    }
                )
            )
        return result

    @staticmethod
    def quality_score(evidence: Evidence, strength: EvidenceStrength) -> float:
        base = {
            EvidenceStrength.DIRECT: 0.98,
            EvidenceStrength.STRONG: 0.88,
            EvidenceStrength.INDIRECT: 0.72,
            EvidenceStrength.SEMANTIC: 0.55,
            EvidenceStrength.INFERRED: 0.45,
            EvidenceStrength.UNCERTAIN: 0.25,
        }[strength]
        if not evidence.location.symbol:
            base -= 0.05
        if not evidence.snippet.strip():
            base -= 0.25
        return max(0.0, min(1.0, base))

    def validate(self, evidence: Evidence, index: IndexedRepository) -> bool:
        if (
            evidence.repository_snapshot_id != index.snapshot_id
            or evidence.commit_sha != index.commit_sha
            or evidence.repository_id != index.repository_id
            or not evidence.content_hash
        ):
            return False
        text = index.file_text.get(evidence.location.file)
        if text is None:
            return False
        lines = text.splitlines()
        if (
            evidence.location.line_start < 1
            or evidence.location.line_end < evidence.location.line_start
            or evidence.location.line_start > len(lines)
            or evidence.location.line_end > len(lines)
        ):
            return False
        from services.repository_analysis.analyzer import content_hash

        snippet = "\n".join(lines[evidence.location.line_start - 1 : evidence.location.line_end])[:4000]
        if content_hash(snippet) != evidence.content_hash or evidence.snippet != snippet:
            return False
        if evidence.location.symbol:
            indexed_symbols = {
                component.location.symbol
                for component in index.components
                if component.location.file == evidence.location.file
                and component.location.line_start == evidence.location.line_start
                and component.location.line_end == evidence.location.line_end
            }
            if evidence.location.symbol not in indexed_symbols:
                return False
        return True

    @staticmethod
    def supports_component_claim(
        evidence: Evidence,
        claim: str,
        component: Component,
        graph: RepositoryGraph | None = None,
        affected_component_ids: set[str] | None = None,
    ) -> bool:
        """Validate lexical support plus the structural role asserted for a component."""
        if evidence.id not in component.evidence_ids or evidence.location.file != component.location.file:
            return False
        if evidence.location.symbol != component.location.symbol:
            return False
        if not EvidenceEngine.supports_claim(evidence, claim):
            return False
        if graph is None or not affected_component_ids or component.id in affected_component_ids:
            return True
        return any(
            (source == component.id and target in affected_component_ids)
            or (target == component.id and source in affected_component_ids)
            for source, target in graph.graph.edges
        )

    @staticmethod
    def supports_claim(evidence: Evidence, claim: str) -> bool:
        """Require claim/evidence concept overlap; provenance alone is not support."""
        ignored = {
            "the", "this", "that", "with", "from", "into", "existing", "proposed",
            "behavior", "change", "current", "requires", "explicit", "verification",
            "processing", "path", "state", "order", "may", "not",
        }
        claim_terms = {word for word in EvidenceEngine._claim_tokens(claim) if word not in ignored}
        evidence_terms = EvidenceEngine._claim_tokens(
            f"{evidence.location.file} {evidence.location.symbol or ''} {evidence.snippet}"
        )
        return bool(claim_terms & evidence_terms)

    @staticmethod
    def _claim_tokens(value: str) -> set[str]:
        import re

        return {
            word[:-1] if word.endswith("s") and len(word) > 4 else word
            for word in re.findall(r"[a-z][a-z0-9_]+", value.lower().replace("_", " "))
            if len(word) >= 4
        }
