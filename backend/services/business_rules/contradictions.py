from __future__ import annotations

import hashlib
import re

from changetrace_schemas import Component, ComponentType, Contradiction, Evidence

_NEGATION = re.compile(r"\b(?:cannot|can't|never|must not|not allowed|prohibited|forbidden|disallow|illegal)\b", re.I)
_PERMISSION = re.compile(r"\b(?:can|may|allowed|permitted|enable|valid)\b", re.I)
_TERMS = re.compile(r"[a-z][a-z0-9_]{3,}", re.I)
_STOP = {"after", "before", "from", "into", "that", "this", "with", "order", "orders"}


_DOMAIN_TERMS = set("cancel cancelled refund refunded ship shipp shipped return returned status inspection modify delete access".split())


class ContradictionDetector:
    """Advanced contradiction detector identifying behavioral oppositions across docs, rules, and code."""

    def detect(
        self,
        components: list[Component],
        evidence: list[Evidence],
        intent: object | None = None,
        state_machines: list[object] | None = None,
    ) -> list[Contradiction]:
        by_id = {item.id: item for item in evidence}
        docs = [item for item in components if item.type == ComponentType.DOCUMENT]
        code = [
            item
            for item in components
            if item.type in {ComponentType.BUSINESS_RULE, ComponentType.API, ComponentType.FUNCTION, ComponentType.TEST}
        ]
        contradictions: list[Contradiction] = []
        seen: set[tuple[str, str]] = set()

        # 1. Document vs Implementation contradictions
        for document in docs:
            doc_evidence = by_id.get(document.evidence_ids[0]) if document.evidence_ids else None
            if not doc_evidence or not _NEGATION.search(doc_evidence.snippet):
                continue
            doc_terms = self._terms(doc_evidence.snippet)
            doc_domain = doc_terms & _DOMAIN_TERMS
            for component in code:
                code_evidence = by_id.get(component.evidence_ids[0]) if component.evidence_ids else None
                if not code_evidence or _NEGATION.search(code_evidence.snippet):
                    continue
                overlap = doc_terms & self._terms(code_evidence.snippet)
                behavior_terms = overlap & _DOMAIN_TERMS
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

        # 2. Code vs Code: Guard / Rule contradictions across functions
        code_rules = [item for item in components if item.type in {ComponentType.BUSINESS_RULE, ComponentType.FUNCTION}]
        for i, c1 in enumerate(code_rules):
            e1 = by_id.get(c1.evidence_ids[0]) if c1.evidence_ids else None
            if not e1:
                continue
            is_neg1 = bool(_NEGATION.search(e1.snippet))
            for c2 in code_rules[i + 1 :]:
                e2 = by_id.get(c2.evidence_ids[0]) if c2.evidence_ids else None
                if not e2 or e1.id == e2.id or e1.location.file == e2.location.file:
                    continue
                is_neg2 = bool(_NEGATION.search(e2.snippet))
                # Opposition: one has negation, the other has permission or unconstrained assignment
                if is_neg1 != is_neg2:
                    terms1 = self._terms(e1.snippet)
                    terms2 = self._terms(e2.snippet)
                    overlap = terms1 & terms2
                    # Meaningful shared behavioral keywords
                    domain_overlap = overlap & {"refund", "cancel", "ship", "return", "access", "modify"}
                    if len(domain_overlap) >= 2 and len(overlap) >= 3:
                        pair = (e1.id, e2.id)
                        if pair not in seen:
                            seen.add(pair)
                            digest = hashlib.sha1(":".join(pair).encode()).hexdigest()[:12]
                            contradictions.append(
                                Contradiction(
                                    id=f"CON-{digest}",
                                    claim=(
                                        f"Conflicting business logic between {e1.location.file} and "
                                        f"{e2.location.file} regarding {', '.join(sorted(domain_overlap))}. "
                                        "One path enforces a restriction while another omits it."
                                    ),
                                    confidence=0.75,
                                    evidence_ids=[e1.id, e2.id],
                                )
                            )

        # 3. Test vs Code contradictions: test asserts rejection but code permits or omits check
        tests = [item for item in components if item.type == ComponentType.TEST]
        for test_item in tests:
            te = by_id.get(test_item.evidence_ids[0]) if test_item.evidence_ids else None
            if not te:
                continue
            test_asserts_rejection = bool(
                re.search(
                    r"\b(assert_raises|raises|rejects|toThrow|status_code\s*==\s*40[134]|forbidden|unauthorized)\b",
                    te.snippet,
                    re.I,
                )
            )
            if not test_asserts_rejection:
                continue
            test_terms = self._terms(te.snippet)
            matching_ces: list[Evidence] = []
            matched_domains: set[str] = set()

            for c in code_rules:
                ce = by_id.get(c.evidence_ids[0]) if c.evidence_ids else None
                if not ce or ce.id == te.id:
                    continue
                overlap = test_terms & self._terms(ce.snippet)
                domain_overlap = overlap & {"cancel", "refund", "delete", "pause"}
                if {"pause", "resume"} <= overlap:
                    domain_overlap.add("resume")
                if len(domain_overlap) >= 1 and len(overlap) >= 2:
                    if not _NEGATION.search(ce.snippet):
                        matching_ces.append(ce)
                        matched_domains |= domain_overlap

            if matching_ces:
                # Group all conflicting code sites for this test into a single contradiction
                target_ids = sorted({ce.id for ce in matching_ces})
                pair_key = (te.id, ":".join(target_ids))
                if pair_key not in seen:
                    seen.add(pair_key)
                    evidence_ids = [te.id] + target_ids[:5]
                    digest = hashlib.sha1(f"{te.id}:{':'.join(target_ids)}".encode()).hexdigest()[:12]
                    site_files = sorted({ce.location.file for ce in matching_ces})
                    files_str = ", ".join(site_files)
                    claim_msg = (
                        f"Test in {te.location.file} expects rejection for "
                        f"{', '.join(sorted(matched_domains))}, but implementation in "
                        f"{files_str} ({len(matching_ces)} site(s)) has no corresponding guard or rejection check."
                    )
                    contradictions.append(
                        Contradiction(
                            id=f"CON-{digest}",
                            claim=claim_msg,
                            confidence=0.80,
                            evidence_ids=evidence_ids,
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
