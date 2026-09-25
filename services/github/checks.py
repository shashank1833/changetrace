from __future__ import annotations

import logging
from typing import Any

import httpx
from changetrace_schemas import AnalysisResult, DecisionStatus

logger = logging.getLogger("changetrace.github.checks")


class GitHubChecksService:
    """Publishes GitHub Check Runs and PR Comments summarizing ChangeTrace simulation results."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def build_summary_markdown(self, result: AnalysisResult) -> str:
        decision_emoji = {
            DecisionStatus.GO: "✅",
            DecisionStatus.REVIEW: "⚠️",
            DecisionStatus.BLOCK: "🛑",
        }.get(result.decision.status, "ℹ️")

        lines = [
            f"## {decision_emoji} ChangeTrace Decision: **{result.decision.status.value}**",
            "",
            "### Rationale",
        ]
        for r in result.decision.rationale:
            lines.append(f"- {r}")

        lines.extend([
            "",
            "### Impact Summary",
            f"- **Affected Files:** {result.impact_summary.affected_files}",
            f"- **Affected Components:** {result.impact_summary.affected_components}",
            f"- **Business Rules:** {result.impact_summary.business_rules}",
            f"- **APIs:** {result.impact_summary.apis}",
            f"- **Database Entities:** {result.impact_summary.database_entities}",
            "",
        ])

        if result.risks:
            lines.append("### Key Risks")
            for risk in sorted(result.risks, key=lambda x: x.risk_score, reverse=True)[:5]:
                conf_pct = int(risk.confidence * 100)
                lines.append(
                    f"- **[{risk.severity.value}]** {risk.title} "
                    f"(Score: {risk.risk_score}/100, Confidence: {conf_pct}%)"
                )
            lines.append("")

        missing_gaps = [g for g in result.test_gaps if g.coverage.value == "MISSING"]
        if missing_gaps:
            lines.append(f"### Missing Verification Tests ({len(missing_gaps)})")
            for gap in missing_gaps[:5]:
                lines.append(f"- **[{gap.priority.value}]** {gap.behavior}")
            lines.append("")

        if result.change_plan:
            lines.append("### Recommended Action Plan")
            for i, step in enumerate(result.change_plan, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        lines.append(f"*Analysis ID: `{result.analysis_id}` | Snapshot: `{result.snapshot_id}`*")
        return "\n".join(lines)

    def create_or_update_check_run(
        self,
        repo_full_name: str,
        head_sha: str,
        result: AnalysisResult,
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> dict[str, Any]:
        auth_token = token or self.token
        if not auth_token:
            logger.info("No token provided; skipping GitHub check run creation (mock mode)")
            return {"status": "skipped", "reason": "no_token"}

        conclusion = {
            DecisionStatus.GO: "success",
            DecisionStatus.REVIEW: "neutral",
            DecisionStatus.BLOCK: "failure",
        }.get(result.decision.status, "neutral")

        summary = self.build_summary_markdown(result)
        body = {
            "name": "ChangeTrace Simulation",
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": {
                "title": f"ChangeTrace: {result.decision.status.value}",
                "summary": summary[:65500],
            },
        }

        url = f"https://api.github.com/repos/{repo_full_name}/check-runs"
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        close_client = False
        if client is None:
            client = httpx.Client(timeout=15.0)
            close_client = True

        try:
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Failed to create GitHub check run: %s", exc)
            return {"status": "error", "error": str(exc)}
        finally:
            if close_client:
                client.close()

    def post_pr_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        result: AnalysisResult,
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> dict[str, Any]:
        auth_token = token or self.token
        if not auth_token:
            logger.info("No token provided; skipping GitHub PR comment (mock mode)")
            return {"status": "skipped", "reason": "no_token"}

        comment_body = self.build_summary_markdown(result)
        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        close_client = False
        if client is None:
            client = httpx.Client(timeout=15.0)
            close_client = True

        try:
            response = client.post(url, json={"body": comment_body}, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Failed to post PR comment: %s", exc)
            return {"status": "error", "error": str(exc)}
        finally:
            if close_client:
                client.close()
