from __future__ import annotations

import json
import statistics
from pathlib import Path

from services.evidence import EvidenceEngine
from tests.evaluation.benchmark.run import f1, matches_expected_finding, ratio
from workers.analysis import AnalysisPipeline

HERE = Path(__file__).parent
REPOSITORY = HERE / "subscription_repository"


def evaluate() -> dict:
    scenarios = json.loads((HERE / "scenarios.json").read_text())
    totals = {key: 0 for key in (
        "impact_tp", "impact_found", "impact_expected", "evidence_tp", "evidence_found",
        "evidence_expected", "gap_tp", "gap_found", "gap_expected", "irrelevant",
        "irrelevant_total", "unsupported", "claims",
    )}
    rows, durations = [], []
    for scenario in scenarios:
        result = AnalysisPipeline().run(REPOSITORY, scenario["change_request"])
        found = {item.location.file for item in result.components}
        expected = set(scenario["directly_affected"] + scenario["transitively_affected"])
        if scenario.get("expected_findings"):
            matched = {
                expectation["file"]
                for expectation in scenario["expected_findings"]
                if any(matches_expected_finding(item, expectation) for item in result.components)
            }
            expected = {item["file"] for item in scenario["expected_findings"]}
        else:
            matched = found & expected
        evidence = {item.location.file for item in result.evidence}
        expected_evidence = set(scenario["expected_evidence"])
        gaps = {item.category for item in result.test_gaps if item.coverage.value == "MISSING"}
        expected_gaps = set(scenario["expected_test_gaps"])
        evidence_by_id = {item.id: item for item in result.evidence}
        unsupported = sum(
            not risk.evidence
            or any(item not in evidence_by_id for item in risk.evidence)
            or not any(
                EvidenceEngine.supports_claim(evidence_by_id[item], risk.claim)
                for item in risk.evidence if item in evidence_by_id
            )
            for risk in result.risks
        )
        values = {
            "impact_tp": len(matched), "impact_found": len(found), "impact_expected": len(expected),
            "evidence_tp": len(evidence & expected_evidence), "evidence_found": len(evidence),
            "evidence_expected": len(expected_evidence), "gap_tp": len(gaps & expected_gaps),
            "gap_found": len(gaps), "gap_expected": len(expected_gaps),
            "irrelevant": len(found & set(scenario["irrelevant"])),
            "irrelevant_total": len(scenario["irrelevant"]), "unsupported": unsupported,
            "claims": len(result.risks),
        }
        for key, value in values.items():
            totals[key] += value
        durations.append(float(result.metrics["analysis_duration"]))
        rows.append({
            "id": scenario["id"], "category": scenario["category"], "found": sorted(found),
            "false_positives": sorted(found - expected), "missing": sorted(expected - matched),
        })
    ip = ratio(totals["impact_tp"], totals["impact_found"])
    ir = ratio(totals["impact_tp"], totals["impact_expected"])
    ep = ratio(totals["evidence_tp"], totals["evidence_found"])
    er = ratio(totals["evidence_tp"], totals["evidence_expected"])
    gp = ratio(totals["gap_tp"], totals["gap_found"])
    gr = ratio(totals["gap_tp"], totals["gap_expected"])
    return {
        "metrics": {
            "scenarios": len(scenarios), "impact_precision": ip, "impact_recall": ir,
            "impact_f1": f1(ip, ir), "evidence_precision": ep, "evidence_recall": er,
            "evidence_f1": f1(ep, er), "test_gap_precision": gp, "test_gap_recall": gr,
            "test_gap_f1": f1(gp, gr),
            "irrelevant_selection_rate": ratio(totals["irrelevant"], totals["irrelevant_total"]),
            "unsupported_claim_rate": ratio(totals["unsupported"], totals["claims"]),
            "median_analysis_seconds": statistics.median(durations),
        },
        "scenarios": rows,
    }


if __name__ == "__main__":
    output = evaluate()
    (HERE / "results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
