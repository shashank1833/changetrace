from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from services.evidence import EvidenceEngine
from workers.analysis import AnalysisPipeline

HERE = Path(__file__).parent
TESTS_ROOT = HERE.parent


def ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 1.0


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def resolve_repository(name: str) -> Path:
    mapping = {
        "demo_repository": TESTS_ROOT / "demo_repository",
        "held_out/fintech_repository": TESTS_ROOT / "held_out" / "fintech_repository",
        "cross_domain/subscription_repository": TESTS_ROOT / "cross_domain" / "subscription_repository",
    }
    repo_path = mapping.get(name)
    if not repo_path or not repo_path.exists():
        raise FileNotFoundError(f"Repository not found for scenario: {name}")
    return repo_path


def evaluate() -> dict:
    scenarios = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
    totals = {
        "impact_tp": 0,
        "impact_found": 0,
        "impact_expected": 0,
        "risk_tp": 0,
        "risk_found": 0,
        "risk_expected": 0,
        "decision_matches": 0,
        "diff_parsed": 0,
        "graph_deltas": 0,
        "unsupported": 0,
        "claims": 0,
        "valid_evidence": 0,
        "evidence_items": 0,
    }
    rows = []
    durations = []

    for scenario in scenarios:
        repo_path = resolve_repository(scenario["repository"])
        diff = scenario["diff"]
        change_request = scenario["change_request"]
        print(f"Running scenario: {scenario['id']} ...")

        start = time.perf_counter()
        result = AnalysisPipeline().run(
            repository_path=repo_path,
            change_request=change_request,
            proposed_diff=diff,
            repository_id=f"pr-eval-{scenario['id']}",
        )
        duration = round(time.perf_counter() - start, 3)
        durations.append(duration)

        found_files = {c.location.file for c in result.components}
        expected_files = set(scenario.get("expected_impacted_files", []))
        impact_tp = len(found_files & expected_files)

        found_risk_text = " ".join(f"{r.title} {r.claim}" for r in result.risks).lower()
        expected_risks = set(scenario.get("expected_risks", []))
        risk_tp = sum(term.lower() in found_risk_text for term in expected_risks) if expected_risks else len(result.risks) == 0

        decision_matched = result.decision.status.value == scenario["expected_decision"]
        diff_parsed = result.change_set is not None and len(result.change_set.files) > 0
        graph_delta_ok = result.graph_delta is not None

        evidence_by_id = {item.id: item for item in result.evidence}
        unsupported = sum(
            not risk.evidence
            or any(item not in evidence_by_id for item in risk.evidence)
            or not any(
                EvidenceEngine.supports_claim(evidence_by_id[item], risk.claim)
                for item in risk.evidence
                if item in evidence_by_id
            )
            for risk in result.risks
        )
        valid_evidence = sum(item.status == "VALID" and bool(item.content_hash) for item in result.evidence)

        # Accumulate totals
        totals["impact_tp"] += impact_tp
        totals["impact_found"] += len(found_files)
        totals["impact_expected"] += len(expected_files)
        totals["risk_tp"] += risk_tp if expected_risks else (1 if len(result.risks) == 0 else 0)
        totals["risk_found"] += len(result.risks)
        totals["risk_expected"] += len(expected_risks) if expected_risks else 1
        totals["decision_matches"] += 1 if decision_matched else 0
        totals["diff_parsed"] += 1 if diff_parsed else 0
        totals["graph_deltas"] += 1 if graph_delta_ok else 0
        totals["unsupported"] += unsupported
        totals["claims"] += len(result.risks)
        totals["valid_evidence"] += valid_evidence
        totals["evidence_items"] += len(result.evidence)

        scenario_impact_prec = ratio(impact_tp, len(found_files))
        scenario_impact_rec = ratio(impact_tp, len(expected_files))
        scenario_risk_prec = 1.0 if (expected_risks and risk_tp > 0 and len(result.risks) > 0) or (not expected_risks and len(result.risks) == 0) else 0.0

        rows.append({
            "id": scenario["id"],
            "title": scenario["title"],
            "category": scenario["category"],
            "diff_parsed": diff_parsed,
            "decision": result.decision.status.value,
            "expected_decision": scenario["expected_decision"],
            "decision_matched": decision_matched,
            "impact_precision": scenario_impact_prec,
            "impact_recall": scenario_impact_rec,
            "risk_precision": scenario_risk_prec,
            "duration_seconds": duration,
        })

    impact_prec = ratio(totals["impact_tp"], totals["impact_found"])
    impact_rec = ratio(totals["impact_tp"], totals["impact_expected"])
    risk_matched = sum(1 for r in rows if r["risk_precision"] > 0)
    risk_prec = ratio(risk_matched, len(rows))
    risk_rec = ratio(totals["risk_tp"], totals["risk_expected"])

    output = {
        "scenarios": len(scenarios),
        "diff_patch_validity_rate": ratio(totals["diff_parsed"], len(scenarios)),
        "graph_delta_success_rate": ratio(totals["graph_deltas"], len(scenarios)),
        "decision_accuracy": ratio(totals["decision_matches"], len(scenarios)),
        "impact_precision": impact_prec,
        "impact_recall": impact_rec,
        "impact_f1": f1(impact_prec, impact_rec),
        "risk_precision": risk_prec,
        "risk_recall": risk_rec,
        "risk_f1": f1(risk_prec, risk_rec),
        "unsupported_claim_rate": ratio(totals["unsupported"], totals["claims"]),
        "evidence_validity_rate": ratio(totals["valid_evidence"], totals["evidence_items"]),
        "median_analysis_seconds": statistics.median(durations),
        "rows": rows,
    }
    return output


if __name__ == "__main__":
    results = evaluate()
    print("\n" + "=" * 60)
    print("ChangeTrace Historical PR Evaluation Harness")
    print("=" * 60)
    print(f"Scenarios Evaluated:         {results['scenarios']}")
    print(f"Diff Patch Validity Rate:    {results['diff_patch_validity_rate']:.4f}")
    print(f"Graph Delta Success Rate:    {results['graph_delta_success_rate']:.4f}")
    print(f"Decision Accuracy:           {results['decision_accuracy']:.4f} ({int(results['decision_accuracy'] * results['scenarios'])}/{results['scenarios']} matched)")
    print(f"Impact Precision:            {results['impact_precision']:.4f}")
    print(f"Impact Recall:               {results['impact_recall']:.4f}")
    print(f"Impact F1:                   {results['impact_f1']:.4f}")
    print(f"Risk Precision:              {results['risk_precision']:.4f}")
    print(f"Risk Recall:                 {results['risk_recall']:.4f}")
    print(f"Risk F1:                     {results['risk_f1']:.4f}")
    print(f"Unsupported Claim Rate:      {results['unsupported_claim_rate']:.4f}")
    print(f"Evidence Validity Rate:      {results['evidence_validity_rate']:.4f}")
    print(f"Median Analysis Duration:    {results['median_analysis_seconds']:.3f} s")
    print("=" * 60)

    for r in results["rows"]:
        status_flag = "PASS" if r["decision_matched"] else "FAIL"
        print(f"[{status_flag}] {r['id']} ({r['category']}) -> Decision: {r['decision']} (Expected: {r['expected_decision']})")

    out_file = HERE / "results.json"
    out_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote results to {out_file}")

    # Enforce quality assertions
    assert results["diff_patch_validity_rate"] == 1.0, "Diff patch validity rate below 1.0"
    assert results["decision_accuracy"] >= 0.80, f"Decision accuracy {results['decision_accuracy']} below 80%"
    assert results["unsupported_claim_rate"] == 0.0, "Unsupported claim rate must be 0.0"
    assert results["evidence_validity_rate"] == 1.0, "Evidence validity rate must be 1.0"
    print("\nHistorical PR evaluation: All scenarios passed within targets.\n")
    sys.exit(0)
