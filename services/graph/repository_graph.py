from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx
from changetrace_schemas import GraphEdge

if TYPE_CHECKING:
    from services.repository_analysis.analyzer import IndexedRepository


class RepositoryGraph:
    def __init__(self, index: IndexedRepository):
        self.graph = nx.DiGraph()
        self.components = {component.id: component for component in index.components}
        self.by_name: dict[str, list[str]] = {}
        self.by_file: dict[str, list[str]] = {}
        for component in index.components:
            self.graph.add_node(component.id, component=component)
            self.by_name.setdefault(component.name.lower(), []).append(component.id)
            self.by_file.setdefault(component.location.file, []).append(component.id)
        self._connect_calls(index)
        self._connect_imports(index)
        self._connect_file_members()

    def _edge(self, source: str, target: str, relationship: str) -> None:
        if source != target:
            self.graph.add_edge(source, target, relationship=relationship)

    def _connect_calls(self, index: IndexedRepository) -> None:
        imported_files = {file: self._imported_files(file, index) for file in self.by_file}
        for caller, called, file in index.calls:
            source_candidates = self.by_name.get(caller.lower(), [])
            sources = [node for node in source_candidates if self.components[node].location.file == file]
            if not sources:
                sources = self.by_file.get(file, [])[:1]
            target_name = called.split(".")[-1].lower()
            candidates = self.by_name.get(target_name, [])
            local = [node for node in candidates if self.components[node].location.file == file]
            imported = [
                node for node in candidates if self.components[node].location.file in imported_files.get(file, set())
            ]
            targets = local or imported
            for source in sources:
                for target in targets:
                    self._edge(source, target, "CALLS")

    def _connect_imports(self, index: IndexedRepository) -> None:
        for source_file in self.by_file:
            source_nodes = self.by_file.get(source_file, [])[:1]
            for file in self._imported_files(source_file, index):
                for source in source_nodes:
                    for target in self.by_file[file][:1]:
                        self._edge(source, target, "IMPORTS")

    def _imported_files(self, source_file: str, index: IndexedRepository) -> set[str]:
        result: set[str] = set()
        for importing_file, imported, _line in index.imports:
            if importing_file != source_file:
                continue
            parts = imported.split(".")
            candidates = ["/".join(parts[:length]) for length in range(len(parts), 0, -1)]
            for file in self.by_file:
                normalized = file.rsplit(".", 1)[0]
                if any(normalized == candidate or normalized.endswith(f"/{candidate}") for candidate in candidates):
                    result.add(file)
                    break
        return result

    def _connect_file_members(self) -> None:
        for nodes in self.by_file.values():
            file_nodes = [node for node in nodes if self.components[node].type.value == "FILE"]
            for file_node in file_nodes:
                for member in nodes:
                    self._edge(file_node, member, "CONTAINS")

    def neighborhood(self, seeds: set[str], depth: int = 2) -> dict[str, int]:
        distances = {seed: 0 for seed in seeds if seed in self.graph}
        frontier = set(distances)
        undirected = self.graph.to_undirected()
        for distance in range(1, depth + 1):
            next_frontier: set[str] = set()
            for node in frontier:
                next_frontier.update(undirected.neighbors(node))
            next_frontier -= distances.keys()
            for node in next_frontier:
                distances[node] = distance
            frontier = next_frontier
        return distances

    def impact_neighborhood(self, seeds: set[str], depth: int = 2) -> dict[str, int]:
        """Traverse dependencies without expanding every sibling through a containing file."""
        distances = {seed: 0 for seed in seeds if seed in self.graph}
        frontier = set(distances)
        terminal_files: set[str] = set()
        for distance in range(1, depth + 1):
            next_frontier: set[str] = set()
            for node in frontier:
                for source, _target, data in self.graph.in_edges(node, data=True):
                    if data["relationship"] == "CONTAINS":
                        distances.setdefault(source, distance)
                        terminal_files.add(source)
                    else:
                        next_frontier.add(source)
                for _source, target, data in self.graph.out_edges(node, data=True):
                    if data["relationship"] != "CONTAINS" or node in seeds:
                        next_frontier.add(target)
            next_frontier -= distances.keys()
            for node in next_frontier:
                distances[node] = distance
            frontier = next_frontier
        return distances

    def edges_for(self, nodes: set[str]) -> list[GraphEdge]:
        return [
            GraphEdge(source=a, target=b, relationship=data["relationship"])
            for a, b, data in self.graph.edges(data=True)
            if a in nodes and b in nodes
        ]

    def directed_path_ranking(self, seeds: set[str], depth: int = 3) -> dict[str, float]:
        """Compute directed path ranking scores from seeds through CALLS, IMPORTS, and CONTAINS edges."""
        scores: dict[str, float] = {seed: 1.0 for seed in seeds if seed in self.graph}
        frontier: dict[str, float] = dict(scores)
        decay = 0.65
        for _ in range(depth):
            next_frontier: dict[str, float] = {}
            for node, current_score in frontier.items():
                for source, _target, data in self.graph.in_edges(node, data=True):
                    rel = data.get("relationship", "")
                    weight = 0.85 if rel == "CALLS" else (0.70 if rel == "IMPORTS" else 0.40)
                    new_score = current_score * decay * weight
                    if new_score > scores.get(source, 0.0):
                        scores[source] = new_score
                        next_frontier[source] = new_score
                for _source, target, data in self.graph.out_edges(node, data=True):
                    rel = data.get("relationship", "")
                    weight = 0.85 if rel == "CALLS" else (0.70 if rel == "IMPORTS" else 0.40)
                    new_score = current_score * decay * weight
                    if new_score > scores.get(target, 0.0):
                        scores[target] = new_score
                        next_frontier[target] = new_score
            frontier = next_frontier
        return scores

    def find_dead_code(self) -> set[str]:
        """Identify dead or unreferenced components that have no callers, imports, or entrypoint roles."""
        from changetrace_schemas import ComponentType

        entry_types = {
            ComponentType.API,
            ComponentType.JOB,
            ComponentType.TEST,
            ComponentType.STATE,
            ComponentType.DOCUMENT,
            ComponentType.FILE,
        }
        entry_nodes = {
            node
            for node, comp in self.components.items()
            if comp.type in entry_types
            or comp.name.startswith("test_")
            or any(kw in comp.name.lower() for kw in ("main", "handler", "run", "cli", "app"))
        }
        reachable: set[str] = set(entry_nodes)
        frontier = set(entry_nodes)
        while frontier:
            next_frontier = set()
            for node in frontier:
                for _source, target, _data in self.graph.out_edges(node, data=True):
                    if target not in reachable:
                        reachable.add(target)
                        next_frontier.add(target)
            frontier = next_frontier

        dead_code = {
            node
            for node, comp in self.components.items()
            if node not in reachable
            and comp.type in {ComponentType.FUNCTION, ComponentType.CLASS}
            and not any(test in comp.location.file for test in ("/test", "test_"))
        }
        return dead_code
