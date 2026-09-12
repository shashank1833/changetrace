from __future__ import annotations

import hashlib
import re

from changetrace_schemas import Component, ComponentType, CoverageStatus, Severity, TestScenario

from services.repository_analysis import IndexedRepository


class TestGapEngine:
    """Derive applicable scenarios and distinguish absence from uncertain coverage."""

    def generate(
        self,
        intent,
        components: list[Component],
        risk_id: str | None,
        index: IndexedRepository | None = None,
    ) -> list[TestScenario]:
        evidence = list(dict.fromkeys(eid for component in components for eid in component.evidence_ids))
        if not evidence:
            return []
        entity = intent.entities[0] if intent.entities else "resource"
        state = intent.states_added[0] if intent.states_added else "proposed state"
        requirement_options = (
            intent.expected_behaviors or intent.constraints or [f"Implement requested change for {entity}"]
        )
        requirement = requirement_options[0]
        types = {component.type for component in components}
        text = " ".join(
            intent.entities
            + intent.actions
            + intent.states_added
            + intent.states_removed
            + intent.constraints
            + intent.expected_behaviors
        ).lower()
        words = set(re.findall(r"[a-z][a-z0-9_]+", text))
        specs: list[tuple[str, str, Severity, set[str]]] = []

        def add(category: str, expected: str, priority: Severity, terms: set[str]) -> None:
            specs.append((category, expected, priority, terms))

        if words & {"add", "display", "expose", "notify", "track", "report"}:
            add("happy path", "the proposed change succeeds", Severity.HIGH, {"happy", "success", "succeeds"})
        if words & {"prevent", "reject", "fails", "failed", "only", "cannot", "invalid"}:
            add(
                "negative path",
                "an invalid change is rejected without side effects",
                Severity.HIGH,
                {"invalid", "reject", "cannot", "raises", "denied", "failure"},
            )
        if words & {"authorize", "authorization", "permission", "customer", "owner", "owned", "administrator"}:
            add(
                "authorization",
                "only an authorized actor can perform the change",
                Severity.HIGH,
                {"authorization", "permission", "owned", "owner", "another", "customer"},
            )
        state_terms = {"transition", "state", "status", "cancel", "cancellation"}
        if intent.states_added or intent.states_removed or words & state_terms:
            add(
                "state transition",
                "invalid predecessor states are rejected",
                Severity.CRITICAL,
                {"transition", "state", "status"},
            )
        if words & {"boundary", "constraint", "concurrent", "approved", "returned_at"}:
            add(
                "boundary",
                "boundary state values preserve the domain invariant",
                Severity.MEDIUM,
                {"boundary", "limit", "constraint", "concurrent", "approved"},
            )
        integration_terms = {"warehouse", "inspection", "payment", "provider", "integration", "timeout"}
        if words & integration_terms or ComponentType.INTEGRATION in types:
            add(
                "integration failure",
                "a downstream failure does not leave inconsistent state",
                Severity.HIGH,
                {"integration", "failure", "timeout", "downstream", "inspection"},
            )
        if words & {"duplicate", "event"} or ComponentType.JOB in types:
            add(
                "duplicate event",
                "repeated event delivery does not repeat side effects",
                Severity.HIGH,
                {"duplicate", "event", "repeated"},
            )
        if words & {"idempotent", "idempotency", "retry", "concurrent", "duplicate"} or ComponentType.JOB in types:
            add(
                "idempotency",
                "retrying the operation produces one business outcome",
                Severity.HIGH,
                {"idempotent", "idempotency", "retry", "duplicate", "concurrent"},
            )
        if words & {"rollback", "fails", "failed", "timeout", "partial"}:
            add(
                "rollback",
                "partial failure rolls back or records a recoverable state",
                Severity.HIGH,
                {"rollback", "partial", "recoverable", "failure", "timeout"},
            )
        if words & {"persist", "record", "records", "consistent", "consistency", "unique", "restock"} or (
            ComponentType.DATABASE in types and words & {"database", "constraint"}
        ):
            add(
                "data consistency",
                "persisted state and dependent records remain consistent",
                Severity.HIGH,
                {"consistency", "database", "persist", "record", "unique"},
            )

        test_components = [component for component in components if component.type == ComponentType.TEST]
        production_names = {
            component.name.lower()
            for component in components
            if component.type not in {ComponentType.FILE, ComponentType.TEST}
        }
        test_details = self._test_details(test_components, index, production_names)
        component_ids = [component.id for component in components[:8]]
        scenarios: list[TestScenario] = []
        for category, expected, priority, coverage_terms in specs:
            coverage = self._coverage(category, coverage_terms, test_details)
            raw = f"{entity}:{state}:{category}"
            scenarios.append(
                TestScenario(
                    scenario_id="TS-" + hashlib.sha1(raw.encode()).hexdigest()[:10],  # noqa: S324
                    priority=priority,
                    category=category,
                    behavior=f"Verify {category} behavior for {requirement}",
                    actor="authorized customer",
                    preconditions=[f"{entity}.status is an allowed predecessor for {state}"],
                    action=f"transition {entity} to {state}",
                    expected_result=expected,
                    invariant=[f"{entity} ownership and data consistency are preserved"],
                    related_requirement=requirement,
                    related_risk=risk_id,
                    evidence=evidence[:6],
                    affected_components=component_ids,
                    why_missing=self._coverage_reason(category, coverage),
                    reason_it_matters=(
                        f"A regression in {category} could violate the requested behavior or domain invariant."
                    ),
                    coverage=coverage,
                )
            )
        return scenarios

    @staticmethod
    def _test_details(
        test_components, index, production_names: set[str]
    ) -> list[tuple[set[str], bool, bool, set[str]]]:
        details = []
        for component in test_components:
            snippet = ""
            if index is not None and component.evidence_ids:
                evidence = next((item for item in index.evidence if item.id == component.evidence_ids[0]), None)
                snippet = evidence.snippet if evidence else ""
            normalized = f"{component.name} {snippet}".lower().replace("_", " ")
            tokens = set(re.findall(r"[a-z][a-z0-9_]+", normalized))
            called = {
                name for name in production_names if re.search(rf"\b{re.escape(name)}\s*\(", snippet, re.I)
            }
            has_assertion = bool(re.search(r"\bassert\b|pytest\.raises|expect\s*\(", snippet, re.I))
            # Parameterized/state-transition and integration tests often express
            # equivalent coverage through values and mocked boundaries rather than
            # category words in the test name.
            signals = set(tokens)
            if re.search(r"parametrize|each\s*\(", snippet, re.I):
                signals.add("parameterized")
            if re.search(r"mock|monkeypatch|timeout|httpx|requests", snippet, re.I):
                signals.add("integration")
            if re.search(r"status|state|transition|created|paid|shipped|cancelled|returned", snippet, re.I):
                signals.add("transition")
            details.append((signals, bool(called), has_assertion, called))
        return details

    @staticmethod
    def _coverage(
        category: str, terms: set[str], details: list[tuple[set[str], bool, bool, set[str]]]
    ) -> CoverageStatus:
        equivalent = {
            "state transition": {"transition", "parameterized"},
            "integration failure": {"integration", "timeout", "failure"},
            "negative path": {"raises", "denied", "invalid", "reject", "failure"},
            "authorization": {"authorization", "permission", "owner", "owned", "denied"},
            "idempotency": {"duplicate", "retry", "idempotent", "parameterized"},
            "duplicate event": {"duplicate", "event", "repeated", "parameterized"},
        }.get(category, set())
        partial = False
        for tokens, calls_affected, has_assertion, _called in details:
            explicit = bool(tokens & terms)
            equivalent_behavior = bool(tokens & equivalent)
            positive_behavior = category == "happy path" and calls_affected
            if has_assertion and calls_affected and (explicit or equivalent_behavior or positive_behavior):
                return CoverageStatus.COVERED
            if explicit or equivalent_behavior or calls_affected:
                partial = True
        if partial:
            return CoverageStatus.PARTIALLY_COVERED
        return CoverageStatus.UNCERTAIN if details else CoverageStatus.MISSING

    @staticmethod
    def _coverage_reason(category: str, coverage: CoverageStatus) -> str:
        if coverage == CoverageStatus.COVERED:
            return f"A discovered test contains assertions and behavioral signals for {category}."
        if coverage == CoverageStatus.PARTIALLY_COVERED:
            return f"A discovered test is related to {category}, but assertion-level coverage is incomplete."
        if coverage == CoverageStatus.UNCERTAIN:
            return f"Tests exist, but deterministic analysis cannot establish coverage for {category}."
        return (
            "No discovered test provides exact, equivalent, parameterized, integration, "
            f"indirect, or state-transition coverage for {category}."
        )
