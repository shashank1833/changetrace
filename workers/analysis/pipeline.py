from __future__ import annotations

import re
import time
from collections import Counter
from pathlib import Path

from changetrace_schemas import (
    AnalysisResult,
    ComponentType,
    CoverageStatus,
    EvidenceStrength,
    ImpactStatus,
    ImpactSummary,
)

from services.business_rules import ContradictionDetector
from services.changes import ChangeInterpreter
from services.decisions import DecisionEngine
from services.evidence import EvidenceEngine
from services.graph import RepositoryGraph
from services.impact import ImpactEngine
from services.repository_analysis import DiffAnalyzer, RepositoryAnalyzer, SnapshotService
from services.risks import AdversarialVerifier, RiskEngine
from services.state_machines import StateMachineAnalyzer
from services.test_gaps import TestGapEngine
from services.verification import ResultVerifier

ANALYZER_VERSION = "0.2.0"


class AnalysisPipeline:
    def run(
        self,
        repository_path: Path,
        change_request: str,
        proposed_diff: str | None = None,
        base_ref: str | None = None,
        target_ref: str | None = None,
        repository_id: str = "unknown",
    ) -> AnalysisResult:
        started = time.perf_counter()
        snapshot = SnapshotService().from_local(repository_path)
        before_index = RepositoryAnalyzer().scan(snapshot.path, snapshot.id, snapshot.commit_sha, repository_id)
        index = before_index
        change_set = graph_delta = None
        temporary = None
        ref_temporary = None
        if base_ref and target_ref:
            proposed_diff, base_sha, target_sha = DiffAnalyzer().compare_refs(snapshot.path, base_ref, target_ref)
            snapshot, ref_temporary = SnapshotService().materialize_git_ref(snapshot.path, base_sha)
            before_index = RepositoryAnalyzer().scan(snapshot.path, snapshot.id, snapshot.commit_sha, repository_id)
        else:
            base_sha, target_sha = snapshot.commit_sha, None
        if proposed_diff:
            diff_analyzer = DiffAnalyzer()
            change_set = diff_analyzer.parse(proposed_diff, snapshot)
            if target_sha:
                change_set = change_set.model_copy(
                    update={"before_commit_sha": base_sha, "after_commit_sha": target_sha}
                )
            temporary = diff_analyzer.materialize_after(snapshot.path, proposed_diff)
            after_path = Path(temporary.name)
            from services.repository_analysis import IncrementalIndexer

            inc_result = IncrementalIndexer().update(
                base_index=before_index,
                new_root=after_path,
                new_snapshot_id=change_set.after_snapshot_id,
                new_commit_sha=change_set.after_commit_sha,
                repository_id=repository_id,
                change_set=change_set,
            )
            index = inc_result.index
            change_set = diff_analyzer.enrich(change_set, before_index, index)
            graph_delta = diff_analyzer.graph_delta(before_index, index)
        intent = ChangeInterpreter().interpret(change_request)
        graph = RepositoryGraph(index)
        discovered, rules, distances = ImpactEngine().discover(index, graph, intent)
        discovered, distances = self._include_changed_components(discovered, distances, index, change_set)
        components = [
            component
            for component in discovered
            if component.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
        ]
        candidates = [component for component in discovered if component.impact_status == ImpactStatus.CANDIDATE]
        rules = ImpactEngine._rules(components, index.snapshot_id)
        evidence = EvidenceEngine().collect(index, components, intent=intent)
        state_machines = StateMachineAnalyzer().discover(index)
        contradictions = ContradictionDetector().detect(
            components, evidence, intent=intent, state_machines=state_machines
        )
        preliminary_test_gaps = TestGapEngine().generate(intent, components, None, index)
        missing_count = sum(gap.coverage == CoverageStatus.MISSING for gap in preliminary_test_gaps)
        risks = RiskEngine().calculate(components, rules, distances, missing_count, state_machines, intent=intent)
        risks = AdversarialVerifier().review(risks, components)
        test_gaps = TestGapEngine().generate(intent, components, risks[0].risk_id if risks else None, index)
        plan = self._plan(intent, components, test_gaps)
        # Retain evidence required by verified findings and direct seed impacts
        finding_evidence_ids: set[str] = set()
        for r in risks:
            finding_evidence_ids.update(r.evidence)
        for c in contradictions:
            finding_evidence_ids.update(c.evidence_ids)
        for gap in test_gaps:
            finding_evidence_ids.update(gap.evidence)
        for c in components:
            if distances.get(c.id, 9) <= 1 and c.impact_status in {ImpactStatus.CONFIRMED, ImpactStatus.LIKELY}:
                finding_evidence_ids.update(c.evidence_ids)
        focused_evidence = [item for item in evidence if item.id in finding_evidence_ids]
        if not focused_evidence:
            focused_evidence = evidence[:15]
        focused_evidence = sorted(
            focused_evidence,
            key=lambda e: (e.status == "VALID", e.quality_score),
            reverse=True,
        )
        decision = DecisionEngine().decide(
            risks, test_gaps, contradictions, plan, components=components, evidence=focused_evidence
        )

        counts = Counter(component.type for component in components)
        result = AnalysisResult(
            repository=snapshot.repository,
            commit_sha=index.commit_sha,
            snapshot_id=index.snapshot_id,
            analyzer_version=ANALYZER_VERSION,
            model_version="deterministic-v1",
            semantic_analysis="DEGRADED",
            change_request=change_request,
            intent=intent,
            change_set=change_set,
            graph_delta=graph_delta,
            impact_summary=ImpactSummary(
                affected_files=len({component.location.file for component in components}),
                affected_components=len(components),
                business_rules=len(rules),
                apis=counts[ComponentType.API],
                database_entities=counts[ComponentType.DATABASE],
                background_jobs=counts[ComponentType.JOB],
                integrations=counts[ComponentType.INTEGRATION],
                related_tests=counts[ComponentType.TEST],
            ),
            components=components,
            candidate_components=candidates,
            graph_edges=graph.edges_for({c.id for c in components}),
            evidence=focused_evidence,
            business_rules=rules,
            state_machines=state_machines,
            contradictions=contradictions,
            risks=risks,
            test_gaps=test_gaps,
            change_plan=plan,
            decision=decision,
            warnings=index.parse_warnings,
            metrics={
                "analysis_duration": round(time.perf_counter() - started, 3),
                "files_analyzed": len(index.file_text),
                "symbols_indexed": len(index.components),
                "graph_nodes": graph.graph.number_of_nodes(),
                "graph_edges": graph.graph.number_of_edges(),
                "changed_files": len(change_set.files) if change_set else 0,
                "candidate_impacts": len(candidates),
                "likely_impacts": len(components),
                "confirmed_impacts": sum(c.impact_status == ImpactStatus.CONFIRMED for c in components),
                "risks_found": len(risks),
                "test_gaps_found": sum(g.coverage == CoverageStatus.MISSING for g in test_gaps),
                "llm_calls": 0,
                "llm_failures": 0,
            },
        )
        verified = ResultVerifier().verify(result, index)
        if temporary:
            temporary.cleanup()
        if ref_temporary:
            ref_temporary.cleanup()
        return verified

    @staticmethod
    def _include_changed_components(components, distances, index, change_set):
        if not change_set:
            return components, distances
        changed_files = {path for change in change_set.files for path in (change.old_path, change.new_path) if path}
        by_id = {component.id: component for component in components}
        for component in index.components:
            if component.location.file in changed_files:
                by_id[component.id] = component.model_copy(
                    update={
                        "reason": "Directly changed by proposed diff",
                        "evidence_strength": EvidenceStrength.DIRECT,
                        "impact_status": ImpactStatus.CONFIRMED,
                        "reasoning_path": ["proposed diff → changed file/symbol"],
                    }
                )
                distances[component.id] = 0
        return list(by_id.values()), distances

    @staticmethod
    def _plan(intent, components, scenarios) -> list[str]:
        plan = []
        state_comps = [c for c in components if c.type == ComponentType.STATE]
        for state in intent.states_added:
            target = f" in {state_comps[0].location.file}" if state_comps else ""
            plan.append(f"Add {state} to domain state definition and serializers{target}")
        if intent.constraints:
            plan.append("Update state-transition validation guards for the requested constraints")

        intent_terms: set[str] = set()
        if intent:
            search_terms = getattr(intent, "search_terms", set())
            if isinstance(search_terms, set):
                intent_terms.update(t.lower() for t in search_terms)
            domain_terms = getattr(intent, "domain_terms", set())
            if isinstance(domain_terms, set):
                intent_terms.update(t.lower() for t in domain_terms)
            for e in getattr(intent, "entities", []):
                intent_terms.add(str(e).lower())
            for a in getattr(intent, "actions", []):
                intent_terms.add(str(a).lower())
            for phrase in getattr(intent, "constraints", []) + getattr(intent, "expected_behaviors", []):
                for word in re.findall(r"[a-z][a-z0-9_]{2,}", str(phrase).lower()):
                    if word not in {"the", "this", "that", "with", "from", "into", "change", "should"}:
                        intent_terms.add(word)

        def relevance(comp: Component) -> int:
            text = f"{comp.name} {comp.location.file}".lower()
            return sum(1 for term in intent_terms if term in text)

        # 1. Frontend / Caller updates
        ui_comps = [
            c
            for c in components
            if c.type in {ComponentType.FUNCTION, ComponentType.CLASS}
            and any(kw in c.location.file.lower() for kw in {"frontend", "pages", "components", "client", "ui"})
        ]
        relevant_ui = sorted(ui_comps, key=relevance, reverse=True)
        relevant_ui = [c for c in relevant_ui if relevance(c) > 0]
        for c in relevant_ui[:2]:
            plan.append(f"Update frontend caller and request payload in {c.name} ({c.location.file})")

        # 2. API route contract & validation
        api_comps = [c for c in components if c.type == ComponentType.API]
        if api_comps:
            relevant_apis = sorted(api_comps, key=relevance, reverse=True)
            targeted_apis = [c for c in relevant_apis if relevance(c) > 0] or relevant_apis[:1]
            for api in targeted_apis[:2]:
                plan.append(f"Update API route contract and validation for {api.name} in {api.location.file}")

        # 3. Core Engine / Business logic updates
        engine_comps = [
            c
            for c in components
            if c.type in {ComponentType.FUNCTION, ComponentType.CLASS}
            and any(kw in f"{c.name} {c.location.file}".lower() for kw in {"engine", "service", "calc", "process", "matcher", "analyzer", "align"})
            and c not in relevant_ui
        ]
        relevant_engines = sorted(engine_comps, key=relevance, reverse=True)
        relevant_engines = [c for c in relevant_engines if relevance(c) > 0]
        for eng in relevant_engines[:2]:
            plan.append(f"Update business logic and scoring in {eng.name} ({eng.location.file})")

        # 4. Database constraints & migrations
        db_comps = [c for c in components if c.type == ComponentType.DATABASE]
        if db_comps:
            relevant_db = sorted(db_comps, key=relevance, reverse=True)
            targeted_db = [c for c in relevant_db if relevance(c) > 0] or (db_comps[:1] if any(term in intent_terms for term in {"db", "database", "table", "schema", "column", "entity", "model"}) else [])
            for db in targeted_db[:1]:
                plan.append(f"Verify database constraints and migration safety for {db.name} in {db.location.file}")
        elif any(c.type == ComponentType.DATABASE for c in components) and any(term in intent_terms for term in {"db", "database", "table", "schema", "column", "entity", "model"}):
            plan.append("Validate database constraints, queries, and migration requirements")

        # 5. Async / Job handling (only when relevant to intent or if async keywords match)
        async_comps = [c for c in components if c.type in {ComponentType.JOB, ComponentType.INTEGRATION}]
        if async_comps:
            relevant_async = [c for c in async_comps if relevance(c) > 0]
            for async_c in relevant_async[:1]:
                plan.append(f"Verify idempotency and async handling for {async_c.name} in {async_c.location.file}")

        # 6. Test scenarios implementation
        uncovered = [s for s in scenarios if s.coverage in {CoverageStatus.MISSING, CoverageStatus.UNCERTAIN}]
        for s in uncovered[:3]:
            plan.append(f"Implement test scenario for {s.category}: {s.expected_result}")

        # 7. Regression check
        plan.append("Run affected regression tests and re-analyze the resulting commit")
        return list(dict.fromkeys(plan))
