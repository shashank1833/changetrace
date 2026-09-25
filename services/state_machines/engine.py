from __future__ import annotations

import ast
import hashlib
import re

from changetrace_schemas import ComponentType, StateMachine, StateTransition

from services.repository_analysis import IndexedRepository

_TS_TYPE_UNION = re.compile(r"(?:export\s+)?type\s+([A-Za-z0-9_]+(?:Status|State))\s*=\s*([^;\n]+)")
_TS_ENUM = re.compile(r"(?:export\s+)?enum\s+([A-Za-z0-9_]+(?:Status|State))\s*\{([^}]+)\}")
_TS_OBJECT_TRANSITIONS = re.compile(r"([A-Z][A-Z0-9_]+)\s*:\s*\[([^\]]+)\]")
_TS_GUARD_FN = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\b(?:status|state)\b[^)]*\)[^{]*\{([^}]+)\}",
    re.DOTALL,
)


class StateMachineAnalyzer:
    """Extract cross-language enum-like states, literal transition maps, side-effects,
    and tests without executing source.
    """

    def discover(self, index: IndexedRepository) -> list[StateMachine]:
        machines: dict[str, tuple[str, set[str], list[StateTransition]]] = {}
        evidence_by_symbol = {item.location.symbol: item.id for item in index.evidence if item.location.symbol}
        evidence_by_file = {item.location.file: item.id for item in index.evidence}
        parsed: list[tuple[str, ast.Module]] = []

        # 1. Discover Python state machines
        for file, text in index.file_text.items():
            if not file.endswith(".py"):
                continue
            try:
                tree = ast.parse(text, filename=file)
            except SyntaxError:
                continue
            parsed.append((file, tree))
            for name, states in self._enums(tree).items():
                machines[name] = (file, states, [])

        all_transitions: list[StateTransition] = []
        for file, tree in parsed:
            all_transitions.extend(self._transitions(tree, evidence_by_symbol, evidence_by_file.get(file)))

        # 2. Discover JavaScript/TypeScript state machines
        js_machines, js_transitions = self._discover_javascript(index, evidence_by_symbol, evidence_by_file)
        all_transitions.extend(js_transitions)

        # Merge or add JavaScript state machines with cross-language normalization
        for js_name, (js_file, js_states, _) in js_machines.items():
            js_entity = js_name.removesuffix("Status").removesuffix("State") or js_name
            matched_key = None
            for existing_name in machines:
                existing_entity = existing_name.removesuffix("Status").removesuffix("State") or existing_name
                if existing_entity.lower() == js_entity.lower():
                    matched_key = existing_name
                    break
            if matched_key:
                # Merge states across languages
                file, existing_states, trans = machines[matched_key]
                machines[matched_key] = (file, existing_states | js_states, trans)
            else:
                machines[js_name] = (js_file, js_states, [])

        # 3. Assemble StateMachine objects
        result: list[StateMachine] = []
        for name, (file, states, _) in machines.items():
            transitions = [item for item in all_transitions if item.from_state in states]
            # Deduplicate transitions
            seen_transitions: set[tuple[str, str, str | None]] = set()
            unique_transitions: list[StateTransition] = []
            for item in transitions:
                key = (item.from_state, item.to_state, item.handler)
                if key not in seen_transitions:
                    seen_transitions.add(key)
                    unique_transitions.append(item)

            raw = f"{index.snapshot_id}:{file}:{name}"
            result.append(
                StateMachine(
                    id="SM-" + hashlib.sha1(raw.encode()).hexdigest()[:12],  # noqa: S324
                    entity=name.removesuffix("Status").removesuffix("State") or name,
                    states=sorted(states),
                    transitions=unique_transitions,
                    repository_snapshot_id=index.snapshot_id,
                )
            )

        # 4. Map tests to transitions
        self._map_tests_to_transitions(result, index)

        return result

    @staticmethod
    def _enums(tree: ast.AST) -> dict[str, set[str]]:
        enums: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {StateMachineAnalyzer._name(base).lower() for base in node.bases}
            if not any(base.endswith("enum") for base in bases):
                continue
            values = set()
            for statement in node.body:
                if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name):
                    target = statement.targets[0].id
                    if target.isupper():
                        values.add(target)
            if values:
                enums[node.name] = values
        return enums

    @classmethod
    def _transitions(
        cls, tree: ast.AST, evidence_by_symbol: dict[str, str], fallback_evidence_id: str | None
    ) -> list[StateTransition]:
        transitions: list[StateTransition] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                source = cls._state_name(key)
                if not source or not isinstance(value, (ast.Set, ast.List, ast.Tuple)):
                    continue
                handler_node = cls._enclosing_handler_node(tree, node)
                handler = handler_node.name if handler_node else None
                evidence_id = evidence_by_symbol.get(handler or "") or fallback_evidence_id
                if not evidence_id:
                    continue
                side_effects = cls._extract_side_effects(handler_node) if handler_node else []
                for item in value.elts:
                    target = cls._state_name(item)
                    if target:
                        transitions.append(
                            StateTransition(
                                from_state=source,
                                to_state=target,
                                handler=handler,
                                side_effects=side_effects,
                                evidence_ids=[evidence_id],
                            )
                        )
        return transitions

    @classmethod
    def _discover_javascript(
        cls,
        index: IndexedRepository,
        evidence_by_symbol: dict[str, str],
        evidence_by_file: dict[str, str],
    ) -> tuple[dict[str, tuple[str, set[str], list[StateTransition]]], list[StateTransition]]:
        machines: dict[str, tuple[str, set[str], list[StateTransition]]] = {}
        transitions: list[StateTransition] = []

        for file, text in index.file_text.items():
            if not any(file.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx")):
                continue

            file_evidence_id = evidence_by_file.get(file)

            # Match TypeScript string unions: type OrderStatus = 'CREATED' | 'PAID' | ...
            for match in _TS_TYPE_UNION.finditer(text):
                name = match.group(1)
                raw_states = match.group(2)
                states = set(re.findall(r"['\"]([A-Z0-9_]+)['\"]", raw_states))
                if states:
                    machines[name] = (file, states, [])

            # Match TypeScript enums: enum OrderStatus { CREATED = 'CREATED', ... }
            for match in _TS_ENUM.finditer(text):
                name = match.group(1)
                body = match.group(2)
                states = set(re.findall(r"\b([A-Z0-9_]{2,})\b", body))
                if states:
                    machines[name] = (file, states, [])

            # Match transition maps: const transitions = { CREATED: ['PAID', 'CANCELLED'] }
            for match in _TS_OBJECT_TRANSITIONS.finditer(text):
                source = match.group(1)
                targets = re.findall(r"['\"]([A-Z0-9_]+)['\"]", match.group(2))
                for target in targets:
                    transitions.append(
                        StateTransition(
                            from_state=source,
                            to_state=target,
                            handler=None,
                            side_effects=[],
                            evidence_ids=[file_evidence_id] if file_evidence_id else [],
                        )
                    )

            # Match TS guard/transition functions: canRequestRefund, canTransition, etc.
            for match in _TS_GUARD_FN.finditer(text):
                fn_name = match.group(1)
                body = match.group(2)
                evidence_id = evidence_by_symbol.get(fn_name) or file_evidence_id
                if not evidence_id:
                    continue
                side_effects: list[str] = []
                if "fetch(" in body or "axios." in body:
                    side_effects.append("network_call")
                if "dispatch(" in body or "setState(" in body:
                    side_effects.append("state_mutation")
                # Look for status equality checks: status === 'CANCELLED'
                checks = re.findall(r"status\s*===\s*['\"]([A-Z0-9_]+)['\"]", body)
                for state in checks:
                    transitions.append(
                        StateTransition(
                            from_state=state,
                            to_state=f"ACTION_{fn_name.upper()}",
                            handler=fn_name,
                            side_effects=side_effects,
                            evidence_ids=[evidence_id],
                        )
                    )

        return machines, transitions

    @staticmethod
    def _extract_side_effects(handler_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        side_effects: list[str] = []
        for node in ast.walk(handler_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr in {"status", "state"}:
                        target_name = StateMachineAnalyzer._name(target)
                        side_effects.append(f"state_assignment: {target_name}")
            elif isinstance(node, ast.Call):
                name = StateMachineAnalyzer._name(node.func).lower()
                if "commit" in name:
                    side_effects.append("db_commit")
                elif "save" in name or "add" in name:
                    side_effects.append(f"db_write: {name}")
                elif any(term in name for term in ("refund", "warehouse", "inspection", "email", "notify", "request")):
                    side_effects.append(f"service_call: {name}")
                elif name in {"requests.post", "requests.get", "httpx.post", "httpx.get"}:
                    side_effects.append(f"http_call: {name}")
        return sorted(set(side_effects))

    @staticmethod
    def _enclosing_handler_node(
        tree: ast.AST, child: ast.AST
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and child in ast.walk(node):
                return node
        return None

    @staticmethod
    def _map_tests_to_transitions(machines: list[StateMachine], index: IndexedRepository) -> None:
        test_components = [
            c for c in index.components
            if c.type == ComponentType.TEST or "/test" in c.location.file or c.location.file.startswith("test")
        ]
        for machine in machines:
            for transition in machine.transitions:
                matched_tests: list[str] = []
                for test in test_components:
                    test_file_text = index.file_text.get(test.location.file, "").lower()
                    test_name_lower = test.name.lower()
                    # Check if test calls or mentions the transition handler
                    if transition.handler and (
                        transition.handler.lower() in test_name_lower
                        or transition.handler.lower() in test_file_text
                    ):
                        matched_tests.append(test.name)
                        continue
                    # Check if test mentions both from_state and to_state
                    from_lower = transition.from_state.lower()
                    to_lower = transition.to_state.lower()
                    if (
                        from_lower in test_name_lower
                        or (from_lower in test_file_text and to_lower in test_file_text)
                    ):
                        matched_tests.append(test.name)
                transition.tests = sorted(set(matched_tests))

    @staticmethod
    def _state_name(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Attribute):
            return node.attr if node.attr.isupper() else None
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isupper():
            return node.value
        return None

    @staticmethod
    def _name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{StateMachineAnalyzer._name(node.value)}.{node.attr}".strip(".")
        return ""
