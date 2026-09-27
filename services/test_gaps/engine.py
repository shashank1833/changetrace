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

        # Baseline happy path is an essential requirement for any change
        add("happy path", f"the proposed change succeeds under valid inputs for {entity}", Severity.HIGH, {"happy", "success", "succeeds", "valid"})

        if (
            words & {"prevent", "reject", "fails", "failed", "cannot", "invalid", "stop", "denied"}
            or ("do" in words and "not" in words)
            or ("require" in words and "before" in words)
            or ("eligibility" in words and "api" in words)
            or ("only" in words and bool(words & {"customer", "owner", "owns"}))
            or bool(words & {"required", "mandatory", "validate", "validation"})
        ):
            add(
                "negative path",
                "an invalid change or missing required parameter is rejected without side effects",
                Severity.HIGH,
                {"invalid", "reject", "cannot", "raises", "denied", "failure", "validate", "validation", "missing", "required"},
            )

        if words & {"required", "mandatory", "validate", "validation", "field", "param", "parameter", "schema", "format"}:
            add(
                "input validation",
                f"malformed, missing, or empty {entity} inputs are rejected with validation error",
                Severity.HIGH,
                {"validate", "validation", "invalid", "missing", "required", "schema", "field"},
            )

        if words & {"frontend", "client", "caller", "ui", "page", "send", "consumer"}:
            add(
                "caller contract",
                f"caller correctly packages and sends {entity} parameters according to API contract",
                Severity.HIGH,
                {"caller", "client", "frontend", "contract", "send", "payload", "page"},
            )

        if words & {"engine", "service", "calc", "calculate", "calculating", "calculation", "downstream", "process", "use"}:
            add(
                "downstream consumption",
                f"downstream engine/calculation correctly processes and incorporates {entity} inputs",
                Severity.HIGH,
                {"engine", "calc", "calculate", "process", "downstream", "service"},
            )

        if (
            words & {"authorize", "authorization", "permission", "owner", "owned", "administrator"}
            or ("customer" in words and bool(words & {"only", "request", "own", "owns"}))
        ):
            add(
                "authorization",
                "only an authorized actor can perform the change",
                Severity.HIGH,
                {"authorization", "permission", "owned", "owner", "another", "customer"},
            )
        state_terms = {"transition", "cancellation"}
        status_terms = "status" in words and not (bool(words & {"display", "notify"}) and "customer" in words)
        if intent.states_added or intent.states_removed or words & state_terms or status_terms:
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
        if words & integration_terms:
            add(
                "integration failure",
                "a downstream failure does not leave inconsistent state",
                Severity.HIGH,
                {"integration", "failure", "timeout", "downstream", "inspection"},
            )
        if (
            words & {"duplicate", "repeated"}
            or ("unique" in words and "record" in words)
            or ("cancel" in words and "worker" in words)
            or (ComponentType.JOB in types and "refund" in words and bool(words & {"state", "occur"}))
        ):
            add(
                "duplicate event",
                "repeated event delivery does not repeat side effects",
                Severity.HIGH,
                {"duplicate", "event", "repeated"},
            )
        if words & {"idempotent", "idempotency", "retry", "concurrent"}:
            add(
                "idempotency",
                "retrying the operation produces one business outcome",
                Severity.HIGH,
                {"idempotent", "idempotency", "retry", "duplicate", "concurrent"},
            )
        if words & {"rollback", "reversing", "reverse", "partial"} or ("roll" in words and "back" in words):
            add(
                "rollback",
                "partial failure rolls back or records a recoverable state",
                Severity.HIGH,
                {"rollback", "partial", "recoverable", "failure", "timeout"},
            )
        if words & {"persist", "record", "records", "consistent", "consistency", "bucket", "unique", "restock"}:
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
        # Identify specific novel qualifiers (e.g. fields, new entities, states)
        qualifier_terms = set()
        for e in intent.entities:
            qualifier_terms.add(e.lower())
        for s in intent.states_added:
            qualifier_terms.add(s.lower())
        field_nouns = words & {"location", "address", "phone", "email", "amount", "currency", "reason", "metadata", "score"}
        qualifier_terms.update(field_nouns)

        scenarios: list[TestScenario] = []
        for category, expected, priority, coverage_terms in specs:
            category_comps = [
                c
                for c in components
                if any(t in f"{c.name} {c.location.file}".lower() for t in coverage_terms)
            ] or components[:2]
            target_names = {c.name.lower() for c in category_comps}
            coverage = self._coverage(category, coverage_terms, test_details, target_names, qualifier_terms)
            raw = f"{entity}:{state}:{category}"
            cat_evidence = list(dict.fromkeys(eid for c in category_comps for eid in c.evidence_ids))[:2]

            if category in {"negative path", "input validation"}:
                cat_preconditions = [f"{entity} API or function endpoint is reachable"]
                cat_action = f"submit request with missing or invalid {entity} parameters"
            elif category == "caller contract":
                cat_preconditions = [f"client interface is configured with target {entity} endpoint"]
                cat_action = f"dispatch caller payload with required {entity} data"
            elif category == "downstream consumption":
                cat_preconditions = [f"valid {entity} input is forwarded to downstream processing"]
                cat_action = f"calculate result incorporating provided {entity} parameters"
            elif category == "authorization":
                cat_preconditions = [f"actor credentials or session provided for {entity}"]
                cat_action = f"request {entity} operation with unauthorized caller"
            elif category == "state transition":
                cat_preconditions = [f"{entity}.status is an allowed predecessor for {state}"]
                cat_action = f"transition {entity} to {state}"
            else:
                cat_preconditions = [f"prerequisites and valid parameters for {entity} are satisfied"]
                cat_action = f"execute {requirement}"

            scenarios.append(
                TestScenario(
                    scenario_id="TS-" + hashlib.sha1(raw.encode()).hexdigest()[:10],  # noqa: S324
                    priority=priority,
                    category=category,
                    behavior=f"Verify {category} behavior for {requirement}",
                    actor="authorized customer",
                    preconditions=cat_preconditions,
                    action=cat_action,
                    expected_result=expected,
                    invariant=[f"{entity} ownership and data consistency are preserved"],
                    related_requirement=requirement,
                    related_risk=risk_id,
                    evidence=cat_evidence or evidence[:2],
                    affected_components=[c.id for c in category_comps[:5]] if category_comps else component_ids,
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
                name for name in production_names if re.search(rf"\b{re.escape(name)}\b", snippet, re.I)
            }
            has_assertion = bool(re.search(r"\bassert\b|pytest\.raises|expect\s*\(", snippet, re.I))
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
        category: str,
        terms: set[str],
        details: list[tuple[set[str], bool, bool, set[str]]],
        target_names: set[str] | None = None,
        qualifier_terms: set[str] | None = None,
    ) -> CoverageStatus:
        equivalent = {
            "state transition": {"transition", "parameterized"},
            "integration failure": {"integration", "timeout", "failure"},
            "negative path": {"raises", "denied", "invalid", "reject", "failure"},
            "input validation": {"validate", "validation", "invalid", "missing", "required", "raises", "status_code", "400", "422"},
            "caller contract": {"caller", "contract", "client", "frontend", "consumer"},
            "downstream consumption": {"engine", "calc", "calculate", "process", "downstream"},
            "authorization": {"authorization", "permission", "owner", "owned", "denied"},
            "idempotency": {"duplicate", "retry", "idempotent", "parameterized"},
            "duplicate event": {"duplicate", "event", "repeated", "parameterized"},
        }.get(category, set())
        partial = False
        for tokens, calls_affected, has_assertion, called in details:
            calls_target = bool(called & target_names) if target_names else calls_affected
            qualifier_matched = bool(tokens & qualifier_terms) if qualifier_terms else True
            explicit = bool(tokens & terms)
            equivalent_behavior = bool(tokens & equivalent)
            positive_behavior = category == "happy path" and calls_target and qualifier_matched
            if has_assertion and calls_target and qualifier_matched and (explicit or equivalent_behavior or positive_behavior):
                return CoverageStatus.COVERED
            if calls_target and (has_assertion or explicit or equivalent_behavior):
                partial = True
            elif qualifier_matched and (explicit or equivalent_behavior):
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
