from __future__ import annotations

import re

from changetrace_schemas import ChangeIntent

STOP_WORDS = set(
    "a an the as to that can after and or be is of for with new add allow successful should when "
    "use using used uses send sends sent sending by at in on from into it its then each every all "
    "any some such than so while do does did doing done will would could must have has had having "
    "been being support supports supported".split()
)
STATE_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
NON_STATE_ACRONYMS = set("API CSV HTTP HTTPS JSON SQL UI URL".split())
ENTITY_HINTS = set(
    "account authorization billing contract currency customer event fee inspection invoice item job "
    "message notification order payment permission product refund report role settlement shipment "
    "status subscription task transaction user warehouse".split()
)
ACTION_HINTS = set("add return refund inspect ship notify authorize process cancel update".split())


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
            entities = sorted({self._singular(w) for w in words if w not in STOP_WORDS and len(w) >= 3 and not w.isdigit()})[:8]
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
        values = list(intent.entities + intent.actions + intent.states_added + intent.states_removed)
        for sentence in intent.constraints + intent.expected_behaviors:
            normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", sentence)
            values.extend(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", normalized))
            values.extend(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", sentence))
            for a, b in re.findall(r"\b([A-Z][a-zA-Z0-9]+)\s+([A-Z][a-zA-Z0-9]+)\b", sentence):
                if a.lower() not in STOP_WORDS and b.lower() not in STOP_WORDS:
                    values.append(f"{a}{b}")
                    values.append(f"{a}_{b}")
        terms: set[str] = set()
        for value in values:
            for subval in value.split("_"):
                subterm = subval.lower().strip()
                if subterm and subterm not in STOP_WORDS:
                    terms.add(subterm)
                    stem = ChangeInterpreter._stem(subterm)
                    if len(stem) >= 4:
                        terms.add(stem)
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
        for suffix in ("ing", "ed", "es", "s", "ment"):
            if word.endswith(suffix) and len(word) > len(suffix) + 3:
                return word[: -len(suffix)]
        return word
