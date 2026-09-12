from __future__ import annotations

import re

from changetrace_schemas import ChangeIntent

STOP_WORDS = {
    "a",
    "an",
    "the",
    "as",
    "to",
    "that",
    "can",
    "after",
    "and",
    "or",
    "be",
    "is",
    "of",
    "for",
    "with",
    "new",
    "add",
    "allow",
    "successful",
    "should",
}
STATE_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
NON_STATE_ACRONYMS = {"API", "CSV", "HTTP", "HTTPS", "JSON", "SQL", "UI", "URL"}
ENTITY_HINTS = {
    "order",
    "refund",
    "warehouse",
    "inspection",
    "payment",
    "notification",
    "customer",
    "shipment",
    "status",
}
ACTION_HINTS = {"add", "return", "refund", "inspect", "ship", "notify", "authorize", "process", "cancel", "update"}


class ChangeInterpreter:
    """Deterministic baseline interpreter used when an LLM is unavailable.

    Provider output may replace this only after strict ChangeIntent validation.
    """

    def interpret(self, request: str) -> ChangeIntent:
        if len(request.strip()) < 10:
            raise ValueError("Change request must contain at least 10 characters")
        lower = request.lower()
        words = re.findall(r"[a-z][a-z0-9_]+", lower)
        entities = sorted({self._singular(word) for word in words if self._singular(word) in ENTITY_HINTS})
        actions = sorted({hint for hint in ACTION_HINTS if re.search(rf"\b{re.escape(hint)}\b", lower)})
        states = sorted(set(STATE_PATTERN.findall(request)) - NON_STATE_ACRONYMS)
        states_removed = states if any(term in lower for term in ("remove", "delete", "deprecate")) else []
        states_added = [] if states_removed else states
        clauses = [clause.strip(" .") for clause in re.split(r"[.;\n]|\band\b", request, flags=re.I) if clause.strip()]
        constraints = [
            c
            for c in clauses
            if any(
                term in c.lower() for term in ("after", "before", "only", "requires", "must", "successful", "cannot")
            )
        ]
        behaviors = [
            c
            for c in clauses
            if any(term in c.lower() for term in ("should", "trigger", "allow", "be refunded", "become"))
        ]
        if not entities:
            entities = sorted({w for w in words if w not in STOP_WORDS and len(w) > 4})[:8]
        return ChangeIntent(
            entities=entities,
            actions=actions,
            states_added=states_added,
            states_removed=states_removed,
            constraints=constraints,
            expected_behaviors=behaviors or clauses[:3],
        )

    @staticmethod
    def search_terms(intent: ChangeIntent) -> set[str]:
        values = intent.entities + intent.actions + intent.states_added + intent.states_removed
        for sentence in intent.constraints + intent.expected_behaviors:
            values.extend(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", sentence))
        terms: set[str] = set()
        for value in values:
            term = value.lower().strip()
            if term and term not in STOP_WORDS:
                terms.add(term)
                stem = ChangeInterpreter._stem(term)
                if len(stem) >= 4:
                    terms.add(stem)
        return terms

    @staticmethod
    def _singular(word: str) -> str:
        return word[:-1] if word.endswith("s") and len(word) > 4 else word

    @staticmethod
    def _stem(word: str) -> str:
        for suffix in ("ing", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) > len(suffix) + 3:
                return word[: -len(suffix)]
        return word
