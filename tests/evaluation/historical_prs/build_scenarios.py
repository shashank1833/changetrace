from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
TESTS_ROOT = HERE.parent


def make_diff(repo_rel: str, file_rel: str, old_snippet: str, new_snippet: str) -> str:
    repo = TESTS_ROOT / repo_rel
    f = repo / file_rel
    orig = f.read_text(encoding="utf-8")
    assert old_snippet in orig, f"{old_snippet!r} not in {file_rel}"
    mod = orig.replace(old_snippet, new_snippet, 1)

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        shutil.copytree(repo, t, dirs_exist_ok=True)
        (t / file_rel).write_text(mod, encoding="utf-8", newline="\n")
        res = subprocess.run(
            ["git", "diff", "--no-index", file_rel, str(t / file_rel)],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        lines = res.stdout.splitlines()
        # Clean diff header to standard git diff
        clean_lines = [
            f"diff --git a/{file_rel} b/{file_rel}",
            f"--- a/{file_rel}",
            f"+++ b/{file_rel}",
        ] + lines[4:]
        diff_text = "\n".join(clean_lines) + "\n"

        # Verify git apply --check passes against fresh copy
        with tempfile.TemporaryDirectory() as check_dir:
            c = Path(check_dir)
            shutil.copytree(repo, c, dirs_exist_ok=True)
            chk = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", "--ignore-space-change", "-"],
                input=diff_text,
                capture_output=True,
                text=True,
                cwd=c,
            )
            assert chk.returncode == 0, f"check failed for {file_rel}: {chk.stderr}"
        return diff_text


def build():
    d1 = make_diff(
        "demo_repository",
        "backend/models/order.py",
        '    SHIPPED = "SHIPPED"\n    CANCELLED = "CANCELLED"',
        '    SHIPPED = "SHIPPED"\n    RETURNED = "RETURNED"\n    CANCELLED = "CANCELLED"',
    )

    d2 = make_diff(
        "held_out/fintech_repository",
        "services/fee_service.py",
        "base_fee += int(amount_cents * 0.01)",
        "base_fee += int(amount_cents * 0.015) + 50",
    )

    d3 = make_diff(
        "held_out/fintech_repository",
        "services/payment_service.py",
        "if record.status != PaymentStatus.AUTHORIZED:",
        "if record.status not in (PaymentStatus.AUTHORIZED, PaymentStatus.INITIALIZED):",
    )

    d4 = make_diff(
        "demo_repository",
        "backend/models/order.py",
        "    inspection_passed: bool",
        '    inspection_passed: bool\n\n    def format_tracking_code(self) -> str:\n        return f"ORD-{self.id:06d}"',
    )

    d5 = make_diff(
        "cross_domain/subscription_repository",
        "backend/models/subscription.py",
        '    ACTIVE = "ACTIVE"\n    PAST_DUE = "PAST_DUE"',
        '    ACTIVE = "ACTIVE"\n    PAUSED = "PAUSED"\n    PAST_DUE = "PAST_DUE"',
    )

    scenarios = [
        {
            "id": "pr-01-order-state-invalidation",
            "repository": "demo_repository",
            "title": "PR #104: Add RETURNED state to order lifecycle",
            "change_request": "Add RETURNED after shipment and allow a refund after inspection.",
            "diff": d1,
            "expected_impacted_files": [
                "backend/models/order.py",
                "backend/services/refund_service.py",
            ],
            "expected_risks": [
                "order",
                "state",
            ],
            "expected_decision": "REVIEW",
            "category": "state_machine_transition",
            "rationale": "Adding RETURNED introduces downstream state machine branching without verified transition safeguards.",
        },
        {
            "id": "pr-02-fintech-fee-surcharge-break",
            "repository": "held_out/fintech_repository",
            "title": "PR #215: Add dynamic international currency fee surcharge",
            "change_request": "Add currency fee surcharge for international payment settlement",
            "diff": d2,
            "expected_impacted_files": [
                "services/fee_service.py",
            ],
            "expected_risks": [
                "currency",
                "settlement",
            ],
            "expected_decision": "REVIEW",
            "category": "financial_calculation",
            "rationale": "Modifying fee calculation affects settlement totals and payment reconciliation invariants.",
        },
        {
            "id": "pr-03-fintech-missing-settlement-guard",
            "repository": "held_out/fintech_repository",
            "title": "PR #288: Allow settlement execution from INITIALIZED state",
            "change_request": "Allow direct settlement from initialized payment status",
            "diff": d3,
            "expected_impacted_files": [
                "services/payment_service.py",
            ],
            "expected_risks": [
                "settlement",
                "currency",
            ],
            "expected_decision": "REVIEW",
            "category": "authorization_bypass",
            "rationale": "Allowing settlement from INITIALIZED bypasses the payment authorization requirement.",
        },
        {
            "id": "pr-04-safe-additive-order-utility",
            "repository": "demo_repository",
            "title": "PR #312: Add helper method to format order tracking reference",
            "change_request": "Add helper method to format order tracking reference without modifying state",
            "diff": d4,
            "expected_impacted_files": [
                "backend/models/order.py",
            ],
            "expected_risks": [],
            "expected_decision": "GO",
            "category": "safe_additive_refactor",
            "rationale": "Pure additive method without state mutations, database schema alterations, or breaking caller changes.",
        },
        {
            "id": "pr-05-subscription-pause-state",
            "repository": "cross_domain/subscription_repository",
            "title": "PR #405: Add PAUSED state to subscription billing lifecycle",
            "change_request": "Add PAUSED state for customer billing subscriptions",
            "diff": d5,
            "expected_impacted_files": [
                "backend/models/subscription.py",
                "backend/services/subscription_service.py",
            ],
            "expected_risks": [
                "state",
                "transition",
            ],
            "expected_decision": "REVIEW",
            "category": "subscription_lifecycle",
            "rationale": "Adding PAUSED state requires validating billing cycle invariants and subscription pause/resume transitions.",
        },
    ]

    out_file = HERE / "scenarios.json"
    out_file.write_text(json.dumps(scenarios, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(scenarios)} verified PR scenarios to {out_file}")


if __name__ == "__main__":
    build()
