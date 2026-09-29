from __future__ import annotations

import io
import keyword
import re
import tokenize

from changetrace_schemas import (
    BusinessRule,
    Component,
    ComponentType,
    EvidenceStrength,
    ImpactStatus,
    RuleClassification,
)

from services.changes import ChangeInterpreter
from services.graph import RepositoryGraph
from services.repository_analysis import IndexedRepository

_GENERIC_TERMS = set(
    "add allow change do from has into make may new not one only order orders process request same send "
    "should state status stop that the this treat two update when while with without backend frontend "
    "endpoint endpoints api apis page pages service services server client controller handler handlers "
    "route routes router routers app application system file files path paths src code component components "
    "module modules layer interface interfaces util utils helper helpers middleware middlewares schema "
    "schemas model models use using used uses where how support supports supported supporting could would must"
    .split()
)
_CODE_WORDS = set(keyword.kwlist) | set(
    "async await bool class def false int none null return self str true".split()
)


class ImpactEngine:
    """Rank lexical candidates, then promote only corroborated dependency impacts.

    A lexical occurrence is a candidate, not proof. Likely impacts require multiple
    independent intent terms or a deterministic relationship to a likely seed.
    """

    def discover(
        self, index: IndexedRepository, graph: RepositoryGraph, intent
    ) -> tuple[list[Component], list[BusinessRule], dict[str, int]]:
        terms = self._contextual_terms(intent)
        evidence_by_id = {item.id: item for item in index.evidence}
        repository_files = set(index.file_text)
        identity_files = {
            term: {
                component.location.file
                for component in index.components
                if component.type != ComponentType.FILE
                and term in self._identity_tokens(f"{component.name} {component.location.file}")
            }
            for term in terms
        }
        domain_terms = {
            term
            for term, files in identity_files.items()
            if len(files) >= 10 or (len(files) >= 4 and len(files) / max(1, len(repository_files)) >= 0.50)
        }
        # If all constituent sub-tokens of a snake_case compound belong to domain terms, the compound is also a domain term
        expanded_domain = set(domain_terms)
        for term in terms:
            parts = term.split("_")
            if len(parts) >= 2 and all(p in domain_terms for p in parts):
                expanded_domain.add(term)
        domain_terms = expanded_domain
        # Do not suppress the sole vocabulary anchor for a request. Domain terms
        # become non-discriminating only when the request also supplies a qualifier.
        if terms <= domain_terms:
            domain_terms.clear()
        lexical: dict[str, tuple[ImpactStatus, int, set[str]]] = {}
        likely_seeds: set[str] = set()

        for component in index.components:
            if component.type == ComponentType.FILE:
                continue
            symbol_terms = self._identity_tokens(component.name)
            file_terms = self._identity_tokens(component.location.file)
            snippet = "\n".join(
                evidence_by_id[evidence_id].snippet
                for evidence_id in component.evidence_ids
                if evidence_id in evidence_by_id
            )
            content_terms = self._source_tokens(snippet, component.location.file)
            symbol_matches = terms & symbol_terms
            file_matches = terms & file_terms
            content_matches = terms & content_terms
            all_matches = symbol_matches | file_matches | content_matches
            intent_words = set().union(
                *(self._tokens(value) for value in intent.constraints + intent.expected_behaviors)
            )
            typed_signal = self._typed_signal(component.type, intent_words, intent)
            if domain_terms and component.type in {
                ComponentType.API,
                ComponentType.DOCUMENT,
                ComponentType.JOB,
                ComponentType.TEST,
            } and not (symbol_matches - domain_terms):
                # Type words such as "API" or "job" identify a boundary, not which
                # endpoint/job is causally relevant in a vocabulary-dense domain.
                typed_signal = False
            if not all_matches and not (
                typed_signal and component.type in {ComponentType.DATABASE, ComponentType.DOCUMENT, ComponentType.STATE}
            ):
                continue

            meaningful_matches = all_matches - domain_terms
            allow_return = "return" in terms
            concepts = {self._concept(term) for term in meaningful_matches if term != "return" or allow_return}
            identity_concepts = {
                self._concept(term) for term in symbol_matches - domain_terms if term != "return" or allow_return
            }
            content_concepts = {
                self._concept(term) for term in content_matches - domain_terms if term != "return"
            }
            corroborated = len(concepts) >= 2 and len(identity_concepts) >= 1
            explicit_state_reference = self._explicit_state_reference(component, all_matches, intent)
            boundary_needs_identity = component.type in {
                ComponentType.API,
                ComponentType.DOCUMENT,
                ComponentType.JOB,
                ComponentType.TEST,
            }
            lexical_likely = corroborated and (not boundary_needs_identity or bool(identity_concepts))
            status = (
                ImpactStatus.LIKELY
                if (lexical_likely or explicit_state_reference)
                else ImpactStatus.CANDIDATE
            )
            score = len(symbol_matches) * 5 + len(file_matches) * 2 + len(content_matches)
            lexical[component.id] = (status, score, all_matches)
            if status == ImpactStatus.LIKELY:
                likely_seeds.add(component.id)

        distances = graph.impact_neighborhood(likely_seeds, depth=2)
        rankings = graph.directed_path_ranking(likely_seeds, depth=3)
        dead_code = graph.find_dead_code()
        selected: dict[str, Component] = {}
        for component_id, (status, _score, matches) in lexical.items():
            source = graph.components[component_id]
            distance = distances.get(component_id)
            relationship = self._causal_relationship(component_id, likely_seeds, graph)
            path_score = rankings.get(component_id, 0.0)

            # Exclude unreachable dead code from being promoted to LIKELY unless explicitly targeted
            explicit_dead_target = bool(terms & {"unused", "dead", "experiment", "preview", "remove", "delete"})
            if component_id in dead_code and status == ImpactStatus.CANDIDATE and not explicit_dead_target:
                status = ImpactStatus.CANDIDATE
                relationship = None

            if status == ImpactStatus.CANDIDATE and distance == 1 and relationship and component_id not in dead_code:
                status = ImpactStatus.LIKELY
                matched_str = ", ".join(sorted(matches))
                reason = f"Likely match on {matched_str}, supported by {relationship} (rank: {round(path_score, 2)})"
                path = [
                    f"CHANGE terms {sorted(matches)}",
                    f"ENTITY {self._entity_label(intent)}",
                    f"RELATIONSHIP {relationship}",
                    f"COMPONENT {source.name}",
                    f"EVIDENCE {source.evidence_ids[0] if source.evidence_ids else 'none'}",
                ]
            else:
                reason = f"{status.value.title()} lexical match on: {', '.join(sorted(matches))}"
                path = [
                    f"CHANGE terms {sorted(matches)}",
                    f"ENTITY {self._entity_label(intent)}",
                    "RELATIONSHIP semantic identity match",
                    f"COMPONENT {source.name}",
                    f"EVIDENCE {source.evidence_ids[0] if source.evidence_ids else 'none'}",
                ]
            strength = EvidenceStrength.STRONG if status == ImpactStatus.LIKELY else EvidenceStrength.SEMANTIC
            selected[component_id] = source.model_copy(
                update={
                    "reason": reason,
                    "evidence_strength": strength,
                    "impact_status": status,
                    "reasoning_path": path,
                }
            )

        # Promote related symbols only inside a file that already has an independently
        # likely symbol. Cross-file IMPORTS adjacency is not enough: it previously
        # pulled callers, callees, tests, and sibling APIs into almost every result.
        likely_files = {
            component.location.file
            for component in selected.values()
            if component.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
        }
        for component_id, (status, _score, matches) in lexical.items():
            current = selected[component_id]
            source = graph.components[component_id]
            encloses_likely = source.type == ComponentType.CLASS and any(
                other.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
                and other.location.file == source.location.file
                and (
                    source.location.line_start <= other.location.line_start <= source.location.line_end
                    or other.name.startswith(f"{source.name}.")
                )
                and other.name != source.name
                for other in selected.values()
            )
            enclosed_by_likely = any(
                other.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
                and other.type == ComponentType.CLASS
                and other.location.file == source.location.file
                and other.location.line_start <= source.location.line_start <= other.location.line_end
                and other.name != source.name
                for other in selected.values()
            )
            calls_likely_in_file = any(
                (graph.graph.has_edge(source.id, other.id) or graph.graph.has_edge(other.id, source.id))
                and other.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
                and other.location.file == source.location.file
                for other in selected.values()
            )
            is_rule_or_state = source.type in {ComponentType.BUSINESS_RULE, ComponentType.STATE}
            causally_connected = encloses_likely or enclosed_by_likely or calls_likely_in_file or is_rule_or_state

            if (
                status != ImpactStatus.CANDIDATE
                or current.impact_status != ImpactStatus.CANDIDATE
                or source.location.file not in likely_files
                or component_id in dead_code
                or not causally_connected
            ):
                continue

            selected[component_id] = source.model_copy(
                update={
                    "reason": f"Likely match on {', '.join(sorted(matches))}, supported by a same-file affected symbol",
                    "evidence_strength": EvidenceStrength.INDIRECT,
                    "impact_status": ImpactStatus.LIKELY,
                    "reasoning_path": [
                        f"CHANGE terms {sorted(matches)}",
                        f"ENTITY {self._entity_label(intent)}",
                        "RELATIONSHIP CONTAINS independently affected symbol",
                        f"COMPONENT {source.name}",
                        f"EVIDENCE {source.evidence_ids[0] if source.evidence_ids else 'none'}",
                    ],
                }
            )

        # State additions affect direct importers of the state definition. This is a
        # directional one-hop dependency, not an undirected graph expansion.
        if intent.states_added or intent.states_removed:
            lexically_related_files = {component.location.file for component in selected.values()}
            state_files = {
                item.location.file
                for item in selected.values()
                if item.type == ComponentType.STATE and item.impact_status == ImpactStatus.LIKELY
            }
            for source, target, data in graph.graph.edges(data=True):
                source_component = graph.components[source]
                target_component = graph.components[target]
                source_text = index.file_text.get(source_component.location.file, "")
                requested_states = intent.states_added + intent.states_removed
                references_requested_state = any(
                    re.search(rf"\b{re.escape(state)}\b", source_text)
                    for state in requested_states
                )
                if (
                    data["relationship"] != "IMPORTS"
                    or target_component.location.file not in state_files
                    or source_component.type != ComponentType.FILE
                    or source_component.location.file not in lexically_related_files
                    or (domain_terms and not references_requested_state)
                ):
                    continue
                selected[source] = source_component.model_copy(
                    update={
                        "reason": f"Directly imports changed state definition from {target_component.location.file}",
                        "evidence_strength": EvidenceStrength.INDIRECT,
                        "impact_status": ImpactStatus.LIKELY,
                        "reasoning_path": [
                            f"CHANGE state {intent.states_added + intent.states_removed}",
                            f"ENTITY {self._entity_label(intent)}",
                            f"RELATIONSHIP IMPORTS {target_component.location.file}",
                            f"COMPONENT {source_component.name}",
                            f"EVIDENCE {source_component.evidence_ids[0]}",
                        ],
                    }
                )
                distances[source] = 1

        # For a state change, a job that directly calls an affected operation is an
        # asynchronous entry point on that same path. Restricting this to explicit
        # state changes avoids promoting every caller for ordinary lexical requests.
        if intent.states_added or intent.states_removed:
            likely_ids = {
                component_id
                for component_id, component in selected.items()
                if component.impact_status == ImpactStatus.LIKELY
            }
            for source, target, data in graph.graph.edges(data=True):
                source_component = graph.components[source]
                if (
                    data["relationship"] == "CALLS"
                    and target in likely_ids
                    and source_component.type == ComponentType.JOB
                ):
                    selected[source] = source_component.model_copy(
                        update={
                            "reason": (
                                f"Background job directly calls affected component {graph.components[target].name}"
                            ),
                            "evidence_strength": EvidenceStrength.INDIRECT,
                            "impact_status": ImpactStatus.LIKELY,
                            "reasoning_path": [
                                f"CHANGE state {intent.states_added + intent.states_removed}",
                                f"ENTITY {self._entity_label(intent)}",
                                f"RELATIONSHIP CALLS {graph.components[target].name}",
                                f"COMPONENT {source_component.name}",
                                f"EVIDENCE {source_component.evidence_ids[0]}",
                            ],
                        }
                    )
                    distances[source] = 1

        components = sorted(
            selected.values(),
            key=lambda item: (
                item.impact_status != ImpactStatus.LIKELY,
                item.location.file,
                item.location.line_start,
                item.id,
            ),
        )
        trusted = [item for item in components if item.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}]
        trusted_distances = {item.id: distances.get(item.id, 0) for item in trusted}
        rules = self._rules(trusted, index.snapshot_id)
        return components, rules, trusted_distances

    @classmethod
    def _contextual_terms(cls, intent) -> set[str]:
        terms = ChangeInterpreter.search_terms(intent) - _GENERIC_TERMS
        # "return" is both a programming verb and a business operation. Treat it
        # as a domain concept only when the request identifies a return/refund/order
        # entity or a returned state. Otherwise (for example, "return a label") it
        # remains discoverable through the other terms but cannot seed return flows.
        entities = {cls._concept(value.lower()) for value in intent.entities}
        states = {cls._concept(value.lower()) for value in intent.states_added + intent.states_removed}
        if not (entities & {"return", "refund", "order"} or "return" in states):
            terms -= {"return", "returned", "returns"}
        concepts = {cls._concept(t) for t in terms}
        return (terms | {c for c in concepts if c}) - _GENERIC_TERMS

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
        raw_tokens = {
            token
            for part in re.findall(r"[A-Za-z][A-Za-z0-9_]*", value)
            for token in part.lower().split("_")
            if len(token) >= 3 and token not in _CODE_WORDS
        }
        concepts = {cls._concept(t) for t in raw_tokens}
        return raw_tokens | concepts

    @staticmethod
    def _concept(term: str) -> str:
        if term in {"return", "returned", "returns"}:
            return "return"
        if term in {"refund", "refunded", "refunds"}:
            return "refund"
        if term in {"cancel", "cancelled", "cancelling", "cancellation", "cancellations"}:
            return "cancel"
        if term in {"inspect", "inspected", "inspecting", "inspection", "inspections"}:
            return "inspect"
        if term in {"admin", "administrator", "administrators"}:
            return "admin"
        if term in {"align", "aligned", "aligning", "alignment", "alignments"}:
            return "align"
        if term in {"ship", "shipped", "shipping", "shipment", "shipments", "shipp"}:
            return "ship"
        return ChangeInterpreter._stem(term)

    @staticmethod
    def _entity_label(intent) -> str:
        return ", ".join(intent.entities) or "requested behavior"

    @classmethod
    def _explicit_state_reference(cls, component: Component, matches: set[str], intent) -> bool:
        """Promote a referenced enum value only when it belongs to the requested entity.

        This recovers predecessor-state dependencies without treating every importer
        of an enum as affected. Uppercase integration results such as APPROVED do not
        match an order state component and therefore cannot trigger this rule.
        """
        if component.type != ComponentType.STATE or not matches:
            return False
        identity = cls._identity_tokens(f"{component.name} {component.location.file}")
        identity_concepts = {cls._concept(term) for term in identity}
        entities = {cls._concept(entity.lower()) for entity in intent.entities}
        entity_anchor = bool(identity_concepts & entities)
        state_words = {
            cls._concept(value.lower())
            for value in intent.states_added + intent.states_removed
        }
        request_words = set().union(
            *(cls._tokens(value) for value in intent.constraints + intent.expected_behaviors)
        )
        explicit_values = state_words | {cls._concept(word) for word in request_words}
        transition_intent = bool(
            bool(intent.states_added or intent.states_removed)
            or set(intent.actions) & {"cancel", "update", "add"}
            or request_words & {"mark", "keep", "send", "notification", "notify", "stop"}
        )
        matched_concepts = {cls._concept(term) for term in matches}
        return transition_intent and entity_anchor and bool(
            identity_concepts & matched_concepts & explicit_values
        )

    @staticmethod
    def _typed_signal(component_type: ComponentType, words: set[str], intent) -> bool:
        role_terms = {
            ComponentType.API: {"api", "endpoint", "operation", "contract", "expose"},
            ComponentType.DATABASE: {"database", "persist", "record", "unique", "constraint", "query"},
            ComponentType.DOCUMENT: {"documentation", "document", "docs"},
            ComponentType.JOB: {"worker", "job", "event", "background"},
            ComponentType.TEST: {"test", "coverage"},
        }
        if component_type == ComponentType.STATE:
            return bool(intent.states_added + intent.states_removed)
        if component_type == ComponentType.DATABASE and (intent.states_added or intent.states_removed):
            return bool(words & {"add", "update", "database", "persist", "constraint"})
        return bool(words & role_terms.get(component_type, set()))

    @staticmethod
    def _causal_relationship(component_id: str, seeds: set[str], graph: RepositoryGraph) -> str | None:
        """Return a concrete adjacent relationship, never an undirected distance label."""
        for source, _target, data in graph.graph.in_edges(component_id, data=True):
            if source in seeds and data["relationship"] == "CALLS":
                return f"CALLS from {graph.components[source].name}"
        for _source, target, data in graph.graph.out_edges(component_id, data=True):
            if target in seeds and data["relationship"] == "CALLS":
                return f"CALLS {graph.components[target].name}"
        return None

    @staticmethod
    def _related_files(file: str, graph: RepositoryGraph) -> set[str]:
        related: set[str] = set()
        for node in graph.by_file.get(file, []):
            for source, _target, data in graph.graph.in_edges(node, data=True):
                if data["relationship"] in {"CALLS", "IMPORTS"}:
                    related.add(graph.components[source].location.file)
            for _source, target, data in graph.graph.out_edges(node, data=True):
                if data["relationship"] in {"CALLS", "IMPORTS"}:
                    related.add(graph.components[target].location.file)
        return related

    @classmethod
    def _identity_tokens(cls, value: str) -> set[str]:
        tokens = cls._tokens(value)
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
        parts = [p.lower() for p in re.findall(r"[A-Za-z][A-Za-z0-9]*", normalized) if len(p) >= 3]
        for i in range(len(parts) - 1):
            tokens.add(f"{parts[i]}_{parts[i + 1]}")
            if any(ch.isupper() for ch in value):
                tokens.add(f"{parts[i]}{parts[i + 1]}")
        if any(ch.isupper() for ch in value):
            clean = re.sub(r"[^A-Za-z0-9]", "", value).lower()
            if len(clean) >= 6:
                tokens.add(clean)
        raw_parts = {
            part for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", normalized) for part in token.lower().split("_")
        }
        if "return" in raw_parts:
            tokens.add("return")
        return tokens

    @classmethod
    def _source_tokens(cls, value: str, file: str) -> set[str]:
        if not file.endswith(".py"):
            return cls._tokens(value)
        try:
            meaningful = []
            for token in tokenize.generate_tokens(io.StringIO(value).readline):
                if token.type == tokenize.COMMENT:
                    continue
                if token.type in {tokenize.NAME, tokenize.STRING}:
                    meaningful.append(token.string)
            return cls._tokens(" ".join(meaningful))
        except (IndentationError, tokenize.TokenError):
            return cls._tokens(value)

    @staticmethod
    def _rules(components: list[Component], snapshot_id: str) -> list[BusinessRule]:
        rules: list[BusinessRule] = []
        for component in components:
            if component.type != ComponentType.BUSINESS_RULE:
                continue
            statement = component.name.removeprefix("rule:")
            rules.append(
                BusinessRule(
                    id=f"R-{component.id[2:]}",
                    statement=f"Current behavior is conditional on: {statement}",
                    classification=RuleClassification.INFERRED,
                    confidence=0.82,
                    evidence_ids=component.evidence_ids,
                    source_locations=[component.location],
                    repository_snapshot_id=snapshot_id,
                )
            )
        return rules
