from __future__ import annotations

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
            index = RepositoryAnalyzer().scan(
                after_path,
                change_set.after_snapshot_id,
                change_set.after_commit_sha,
                repository_id,
            )
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
        evidence = EvidenceEngine().collect(index, components)
        state_machines = StateMachineAnalyzer().discover(index)
        contradictions = ContradictionDetector().detect(components, evidence)
        preliminary_test_gaps = TestGapEngine().generate(intent, components, None, index)
        missing_count = sum(gap.coverage == CoverageStatus.MISSING for gap in preliminary_test_gaps)
        risks = RiskEngine().calculate(components, rules, distances, missing_count, state_machines)
        risks = AdversarialVerifier().review(risks, components)
        test_gaps = TestGapEngine().generate(intent, components, risks[0].risk_id if risks else None, index)
        plan = self._plan(intent, components, test_gaps)
        decision = DecisionEngine().decide(risks, test_gaps, contradictions, plan)
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
            evidence=evidence,
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
        for state in intent.states_added:
            plan.append(f"Add {state} to the domain state definition and serializers")
        if intent.constraints:
            plan.append("Update state-transition validation for the requested constraints")
        types = {component.type for component in components}
        if ComponentType.DATABASE in types:
            plan.append("Validate database constraints, queries, and migration requirements")
        if ComponentType.API in types:
            plan.append("Update and contract-test affected API behavior")
        if ComponentType.JOB in types or ComponentType.INTEGRATION in types:
            plan.append("Verify asynchronous and external integration behavior")
        missing = sum(s.coverage == CoverageStatus.MISSING for s in scenarios)
        if missing:
            plan.append(f"Implement {missing} focused missing test scenarios")
        plan.append("Run affected regression tests and re-analyze the resulting commit")
        return list(dict.fromkeys(plan))
