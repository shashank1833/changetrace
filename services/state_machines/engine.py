from __future__ import annotations

import ast
import hashlib

from changetrace_schemas import StateMachine, StateTransition

from services.repository_analysis import IndexedRepository


class StateMachineAnalyzer:
    """Extract enum-like states and literal transition maps without executing source."""

    def discover(self, index: IndexedRepository) -> list[StateMachine]:
        machines: dict[str, tuple[str, set[str], list[StateTransition]]] = {}
        evidence_by_symbol = {item.location.symbol: item.id for item in index.evidence if item.location.symbol}
        parsed: list[tuple[str, ast.AST]] = []
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
        all_transitions = [
            transition for _file, tree in parsed for transition in self._transitions(tree, evidence_by_symbol)
        ]
        result: list[StateMachine] = []
        for name, (file, states, _) in machines.items():
            transitions = [item for item in all_transitions if item.from_state in states]
            raw = f"{index.snapshot_id}:{file}:{name}"
            result.append(
                StateMachine(
                    id="SM-" + hashlib.sha1(raw.encode()).hexdigest()[:12],  # noqa: S324
                    entity=name.removesuffix("Status").removesuffix("State") or name,
                    states=sorted(states),
                    transitions=transitions,
                    repository_snapshot_id=index.snapshot_id,
                )
            )
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

    @staticmethod
    def _transitions(tree: ast.AST, evidence_by_symbol: dict[str, str]) -> list[StateTransition]:
        transitions: list[StateTransition] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                source = StateMachineAnalyzer._state_name(key)
                if not source or not isinstance(value, (ast.Set, ast.List, ast.Tuple)):
                    continue
                handler = StateMachineAnalyzer._enclosing_handler(tree, node)
                evidence_id = evidence_by_symbol.get(handler or "")
                if not evidence_id:
                    continue
                for item in value.elts:
                    target = StateMachineAnalyzer._state_name(item)
                    if target:
                        transitions.append(
                            StateTransition(
                                from_state=source,
                                to_state=target,
                                handler=handler,
                                side_effects=[],
                                evidence_ids=[evidence_id],
                            )
                        )
        return transitions

    @staticmethod
    def _enclosing_handler(tree: ast.AST, child: ast.AST) -> str | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and child in ast.walk(node):
                return node.name
        return None

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
