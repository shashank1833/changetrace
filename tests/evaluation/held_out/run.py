from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from services.evidence import EvidenceEngine
from tests.evaluation.benchmark.run import f1, matches_expected_finding, ratio
from workers.analysis import AnalysisPipeline

HERE = Path(__file__).parent
REPOSITORY = HERE / "fintech_repository"


def evaluate() -> dict:
    scenarios = json.loads((HERE / "scenarios.json").read_text())
    totals = {
        key: 0
        for key in (
            "impact_tp",
            "impact_found",
            "impact_expected",
            "evidence_tp",
            "evidence_found",
            "evidence_expected",
            "risk_tp",
            "risk_found",
            "risk_expected",
            "known_fp_found",
            "known_fp_total",
            "unsupported",
            "claims",
            "valid_evidence",
            "evidence_items",
        )
    }
    rows, durations = [], []
    for scenario in scenarios:
        result = AnalysisPipeline().run(REPOSITORY, scenario["change_request"])
        found_files = {item.location.file for item in result.components}
        evidence_files = {item.location.file for item in result.evidence}

        expected_findings = scenario.get("expected_findings", [])
        matched = {
            exp["file"]
            for exp in expected_findings
            if any(matches_expected_finding(item, exp) for item in result.components)
        }
        expected_files = {item["file"] for item in expected_findings}

        expected_evidence = set(scenario.get("expected_important_evidence", []))
        found_risk_text = " ".join(f"{r.title} {r.claim}" for r in result.risks).lower()
        expected_risks = set(scenario.get("expected_risks", []))
        known_fp = set(scenario.get("known_false_positives", []))

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

        impact_tp = len(matched)
        evidence_tp = len(evidence_files & expected_evidence)
        risk_tp = sum(term.lower() in found_risk_text for term in expected_risks)

        values = {
            "impact_tp": impact_tp,
            "impact_found": len(found_files),
            "impact_expected": len(expected_files),
            "evidence_tp": evidence_tp,
            "evidence_found": len(evidence_files),
            "evidence_expected": len(expected_evidence),
            "risk_tp": risk_tp,
            "risk_found": len(result.risks),
            "risk_expected": len(expected_risks),
            "known_fp_found": len(found_files & known_fp),
            "known_fp_total": len(known_fp),
            "unsupported": unsupported,
            "claims": len(result.risks),
            "valid_evidence": valid_evidence,
            "evidence_items": len(result.evidence),
        }
        for k, v in values.items():
            totals[k] += v

        durations.append(float(result.metrics["analysis_duration"]))
        rows.append({
            "id": scenario["id"],
            "impact_precision": ratio(impact_tp, len(found_files)),
            "impact_recall": ratio(impact_tp, len(expected_files)),
            "risk_precision": ratio(risk_tp, len(result.risks)),
        })

    impact_prec = ratio(totals["impact_tp"], totals["impact_found"])
    impact_rec = ratio(totals["impact_tp"], totals["impact_expected"])
    evidence_prec = ratio(totals["evidence_tp"], totals["evidence_found"])
    risk_prec = ratio(totals["risk_tp"], totals["risk_found"])

    output = {
        "scenarios": len(scenarios),
        "impact_precision": impact_prec,
        "impact_recall": impact_rec,
        "impact_f1": f1(impact_prec, impact_rec),
        "evidence_precision": evidence_prec,
        "risk_precision": risk_prec,
        "false_positive_rate": ratio(totals["known_fp_found"], totals["known_fp_total"]),
        "unsupported_claim_rate": ratio(totals["unsupported"], totals["claims"]),
        "evidence_validity_rate": ratio(totals["valid_evidence"], totals["evidence_items"]),
        "median_analysis_seconds": statistics.median(durations),
        "rows": rows,
    }
    return output


if __name__ == "__main__":
    metrics = evaluate()
    print(json.dumps(metrics, indent=2))
    output_path = HERE / "results.json"
    output_path.write_text(json.dumps(metrics, indent=2) + "\n")
    # Assert acceptable production thresholds
    assert metrics["impact_precision"] >= 0.20, f"Impact precision {metrics['impact_precision']} below minimum"
    assert metrics["evidence_validity_rate"] >= 0.95, "Evidence validity rate below 95%"
    assert metrics["unsupported_claim_rate"] <= 0.25, "Unsupported claim rate exceeds 25%"
    print("\nHeld-out benchmark passed production validation!")
    sys.exit(0)

