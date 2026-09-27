from __future__ import annotations

import json

from changetrace_schemas import AnalysisResult, CoverageStatus


class ReportExporter:
    @staticmethod
    def json(result: AnalysisResult) -> str:
        return json.dumps(result.model_dump(mode="json"), indent=2)

    @staticmethod
    def markdown(result: AnalysisResult) -> str:
        lines = [
            f"# ChangeTrace report: {result.repository}",
            "",
            f"- Snapshot: `{result.snapshot_id}`",
            f"- Commit: `{result.commit_sha}`",
            f"- Decision: **{result.decision.status.value}**",
            "",
            "## Proposed change",
            result.change_request,
        ]
        if result.change_set:
            lines.extend(
                [
                    "",
                    "## Diff summary",
                    f"- Source: {result.change_set.source}",
                    f"- Files changed: {len(result.change_set.files)}",
                    f"- Before: `{result.change_set.before_commit_sha}`",
                    f"- After: `{result.change_set.after_commit_sha}`",
                ]
            )
        lines.extend(["", "## Impact summary"])
        lines.extend(
            f"- {key.replace('_', ' ').title()}: {value}" for key, value in result.impact_summary.model_dump().items()
        )
        lines.extend(["", "## Business rules"])
        lines.extend(
            f"- [{rule.classification.value}] {rule.statement} ({rule.confidence:.0%})"
            for rule in result.business_rules
        )
        lines.extend(["", "## Risks"])
        for risk in result.risks:
            lines.extend(
                [
                    f"### {risk.severity.value}: {risk.title}",
                    f"Score {risk.risk_score}/100 · confidence {risk.confidence:.0%} · "
                    f"evidence {risk.evidence_strength.value}",
                    risk.claim,
                    f"Support: {risk.support_status.value}",
                    f"Evidence IDs: {', '.join(risk.evidence)}",
                    f"Recommended: {risk.recommended_action}",
                ]
            )
        if result.contradictions:
            lines.extend(["", "## Contradictions"])
            lines.extend(
                f"- {item.claim} ({item.confidence:.0%}) — {', '.join(item.evidence_ids)}"
                for item in result.contradictions
            )
        lines.extend(["", "## Missing tests"])
        lines.extend(
            f"- **{item.priority.value} / {item.category}:** {item.expected_result}. {item.why_missing}"
            for item in result.test_gaps
            if item.coverage != CoverageStatus.COVERED
        )
        lines.extend(["", "## Recommended actions"])
        lines.extend(f"{number}. {step}" for number, step in enumerate(result.change_plan, 1))
        lines.extend(["", "## Decision rationale"])
        for reason in result.decision.rationale:
            clean = reason.strip()
            if clean.startswith("+ ") or clean.startswith("- "):
                lines.append(f"  - `{clean[0]}` {clean[2:]}")
            elif clean == "Decision Drivers:":
                lines.append(f"- **{clean}**")
            elif clean.startswith("Risk Score:"):
                lines.append(f"- **{clean}**")
            elif clean.startswith("Evidence:"):
                lines.append(f"- **Evidence:** {clean[9:].strip()}")
            else:
                lines.append(f"- {clean}")
        return "\n\n".join(lines)
