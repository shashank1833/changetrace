from __future__ import annotations

import hashlib
import re

from changetrace_schemas import Component, ComponentType, Contradiction, Evidence

_NEGATION = re.compile(r"\b(?:cannot|can't|never|must not|not allowed|prohibited)\b", re.I)
_TERMS = re.compile(r"[a-z][a-z0-9_]{3,}", re.I)
_STOP = {"after", "before", "from", "into", "that", "this", "with", "order", "orders"}


class ContradictionDetector:
    """Conservative lexical detector requiring documentation and implementation evidence."""

    def detect(self, components: list[Component], evidence: list[Evidence]) -> list[Contradiction]:
        by_id = {item.id: item for item in evidence}
        docs = [item for item in components if item.type == ComponentType.DOCUMENT]
        code = [
            item
            for item in components
            if item.type in {ComponentType.BUSINESS_RULE, ComponentType.API, ComponentType.FUNCTION, ComponentType.TEST}
        ]
        contradictions: list[Contradiction] = []
        seen: set[tuple[str, str]] = set()
        for document in docs:
            doc_evidence = by_id.get(document.evidence_ids[0]) if document.evidence_ids else None
            if not doc_evidence or not _NEGATION.search(doc_evidence.snippet):
                continue
            doc_terms = self._terms(doc_evidence.snippet)
            doc_domain = doc_terms & {
                "cancel",
                "cancelled",
                "refund",
                "refunded",
                "ship",
                "shipp",
                "shipped",
                "return",
                "returned",
                "status",
                "inspection",
            }
            for component in code:
                code_evidence = by_id.get(component.evidence_ids[0]) if component.evidence_ids else None
                if not code_evidence or _NEGATION.search(code_evidence.snippet):
                    continue
                overlap = doc_terms & self._terms(code_evidence.snippet)
                behavior_terms = overlap & {
                    "cancel",
                    "cancelled",
                    "refund",
                    "refunded",
                    "ship",
                    "shipped",
                    "return",
                    "returned",
                    "status",
                    "inspection",
                }
                code_terms = self._terms(code_evidence.snippet)
                same_behavior = len(behavior_terms) >= 2
                refund_after_shipment = (
                    bool({"ship", "shipp", "shipped"} & doc_domain)
                    and "refund" in doc_domain
                    and "refund" in code_terms
                    and bool({"ship", "shipp", "shipped"} & code_terms)
                )
                if not same_behavior and not refund_after_shipment:
                    continue
                pair = (doc_evidence.id, code_evidence.id)
                if pair in seen:
                    continue
                seen.add(pair)
                digest = hashlib.sha1(":".join(pair).encode()).hexdigest()[:12]  # noqa: S324
                contradictions.append(
                    Contradiction(
                        id=f"CON-{digest}",
                        claim=(
                            f"Documentation in {doc_evidence.location.file} contains a prohibition, while "
                            f"{code_evidence.location.file} contains a related implementation path without "
                            "the same restriction. Manual confirmation is required."
                        ),
                        confidence=min(0.9, 0.55 + len(behavior_terms) * 0.08),
                        evidence_ids=[doc_evidence.id, code_evidence.id],
                    )
                )
        return contradictions[:10]

    @staticmethod
    def _terms(value: str) -> set[str]:
        result = {term.lower() for term in _TERMS.findall(value.replace("_", " "))} - _STOP
        expanded = set(result)
        for term in result:
            for suffix in ("ed", "ing", "s"):
                if term.endswith(suffix) and len(term) > len(suffix) + 3:
                    expanded.add(term[: -len(suffix)])
        return expanded
