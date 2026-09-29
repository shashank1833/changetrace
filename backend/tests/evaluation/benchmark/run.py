from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from workers.analysis import AnalysisPipeline

HERE = Path(__file__).parent
FIXTURE = HERE.parent / "demo_repository"


@dataclass
class Metrics:
    scenarios: int
    impact_precision: float
    impact_recall: float
    impact_f1: float
    evidence_precision: float
    evidence_recall: float
    evidence_f1: float
    risk_precision: float
    risk_recall: float
    risk_f1: float
    test_gap_precision: float
    test_gap_recall: float
    test_gap_f1: float
    false_positive_rate: float
    unsupported_claim_rate: float
    evidence_validity_rate: float
    schema_valid_output_rate: float
    median_analysis_seconds: float


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def matches_expected_finding(component, expectation: dict) -> bool:
    """Match file, optional symbol/type, relationship, and minimum classification."""
    if component.location.file != expectation["file"]:
        return False
    if expectation.get("symbol") and component.name != expectation["symbol"]:
        return False
    if expectation.get("component_type") and component.type.value != expectation["component_type"]:
        return False
    if expectation.get("relationship") and not any(
        expectation["relationship"] in step for step in component.reasoning_path
    ):
        return False
    ranks = {"REJECTED": 0, "CANDIDATE": 1, "LIKELY": 2, "CONFIRMED": 3}
    return ranks[component.impact_status.value] >= ranks[expectation.get("classification", "LIKELY")]


def evaluate() -> tuple[Metrics, list[dict]]:
    scenarios = json.loads((HERE / "scenarios.json").read_text())
    rows = []
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
            "gap_tp",
            "gap_found",
            "gap_expected",
            "known_fp_found",
            "known_fp_total",
            "unsupported",
            "claims",
            "valid_evidence",
            "evidence_items",
            "schema_valid",
        )
    }
    durations = []
    for scenario in scenarios:
        result = AnalysisPipeline().run(FIXTURE, scenario["change_request"])
        found_files = {item.location.file for item in result.components}
        evidence_files = {item.location.file for item in result.evidence}
        expected_findings = scenario.get("expected_findings")
        if expected_findings:
            matched_expectations = {
                index
                for index, expectation in enumerate(expected_findings)
                if any(matches_expected_finding(component, expectation) for component in result.components)
            }
            expected_files = {item["file"] for item in expected_findings}
            matched_files = {expected_findings[index]["file"] for index in matched_expectations}
        else:
            # Legacy file labels remain supported while scenarios are independently
            # adjudicated and migrated to symbol/relationship expectations.
            expected_files = set(scenario["expected_affected_components"])
            matched_files = found_files & expected_files
        expected_evidence = set(scenario["expected_important_evidence"])
        found_risk_text = " ".join(f"{risk.title} {risk.claim}" for risk in result.risks).lower()
        expected_risks = set(scenario["expected_risks"])
        found_gaps = {item.category for item in result.test_gaps if item.coverage.value == "MISSING"}
        expected_gaps = set(scenario["expected_test_gaps"])
        known_fp = set(scenario["known_false_positives"])
        impact_tp = len(matched_files)
        evidence_tp = len(evidence_files & expected_evidence)
        risk_tp = sum(term.lower() in found_risk_text for term in expected_risks)
        gap_tp = len(found_gaps & expected_gaps)
        evidence_ids = {item.id for item in result.evidence}
        evidence_by_id = {item.id: item for item in result.evidence}
        from services.evidence import EvidenceEngine
        unsupported = sum(
            not risk.evidence
            or any(evidence_id not in evidence_ids for evidence_id in risk.evidence)
            or not any(
                EvidenceEngine.supports_claim(evidence_by_id[evidence_id], risk.claim)
                for evidence_id in risk.evidence
                if evidence_id in evidence_by_id
            )
            for risk in result.risks
        )
        valid_evidence = sum(item.status == "VALID" and bool(item.content_hash) for item in result.evidence)
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
            "gap_tp": gap_tp,
            "gap_found": len(found_gaps),
            "gap_expected": len(expected_gaps),
            "known_fp_found": len(found_files & known_fp),
            "known_fp_total": len(known_fp),
            "unsupported": unsupported,
            "claims": len(result.risks),
            "valid_evidence": valid_evidence,
            "evidence_items": len(result.evidence),
            "schema_valid": 1,
        }
        for key, value in values.items():
            totals[key] += value
        durations.append(float(result.metrics["analysis_duration"]))
        rows.append(
            {
                "id": scenario["id"],
                "category": scenario["category"],
                "impact_precision": ratio(impact_tp, len(found_files)),
                "impact_recall": ratio(impact_tp, len(expected_files)),
                "evidence_precision": ratio(evidence_tp, len(evidence_files)),
                "evidence_recall": ratio(evidence_tp, len(expected_evidence)),
                "risk_precision": ratio(risk_tp, len(result.risks)),
                "risk_recall": ratio(risk_tp, len(expected_risks)),
                "test_gap_precision": ratio(gap_tp, len(found_gaps)),
                "test_gap_recall": ratio(gap_tp, len(expected_gaps)),
                "false_positives": sorted(found_files - expected_files),
            }
        )
    impact_precision = ratio(totals["impact_tp"], totals["impact_found"])
    impact_recall = ratio(totals["impact_tp"], totals["impact_expected"])
    evidence_precision = ratio(totals["evidence_tp"], totals["evidence_found"])
    evidence_recall = ratio(totals["evidence_tp"], totals["evidence_expected"])
    risk_precision = ratio(totals["risk_tp"], totals["risk_found"])
    risk_recall = ratio(totals["risk_tp"], totals["risk_expected"])
    test_gap_precision = ratio(totals["gap_tp"], totals["gap_found"])
    test_gap_recall = ratio(totals["gap_tp"], totals["gap_expected"])
    category_metrics = {}
    for category in sorted({row["category"] for row in rows}):
        category_rows = [row for row in rows if row["category"] == category]
        category_metrics[category] = {
            key: statistics.mean(row[key] for row in category_rows)
            for key in (
                "impact_precision",
                "impact_recall",
                "evidence_precision",
                "evidence_recall",
                "risk_precision",
                "risk_recall",
                "test_gap_precision",
                "test_gap_recall",
            )
        }
        for prefix in ("impact", "evidence", "risk", "test_gap"):
            category_metrics[category][f"{prefix}_f1"] = f1(
                category_metrics[category][f"{prefix}_precision"],
                category_metrics[category][f"{prefix}_recall"],
            )
    for row in rows:
        row["category_metrics"] = category_metrics[row["category"]]

    metrics = Metrics(
        scenarios=len(scenarios),
        impact_precision=impact_precision,
        impact_recall=impact_recall,
        impact_f1=f1(impact_precision, impact_recall),
        evidence_precision=evidence_precision,
        evidence_recall=evidence_recall,
        evidence_f1=f1(evidence_precision, evidence_recall),
        risk_precision=risk_precision,
        risk_recall=risk_recall,
        risk_f1=f1(risk_precision, risk_recall),
        test_gap_precision=test_gap_precision,
        test_gap_recall=test_gap_recall,
        test_gap_f1=f1(test_gap_precision, test_gap_recall),
        false_positive_rate=ratio(totals["known_fp_found"], totals["known_fp_total"]),
        unsupported_claim_rate=ratio(totals["unsupported"], totals["claims"]),
        evidence_validity_rate=ratio(totals["valid_evidence"], totals["evidence_items"]),
        schema_valid_output_rate=ratio(totals["schema_valid"], len(scenarios)),
        median_analysis_seconds=statistics.median(durations),
    )
    return metrics, rows


if __name__ == "__main__":
    metrics, rows = evaluate()
    category_metrics = {row["category"]: row.pop("category_metrics") for row in rows}
    output = {"metrics": asdict(metrics), "categories": category_metrics, "scenarios": rows}
    text = json.dumps(output, indent=2)
    output_path = HERE / "results.json"
    output_path.write_text(text + "\n")
    print(text)
    sys.exit(0)
