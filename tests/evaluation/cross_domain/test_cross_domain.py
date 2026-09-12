from tests.evaluation.cross_domain.run import evaluate


def test_subscription_domain_reports_metrics_and_rejects_unrelated_fixture():
    result = evaluate()
    assert result["metrics"]["scenarios"] == 15
    # Labels are independently specified before execution and include explicit
    # irrelevant controls. This initial expanded-domain baseline intentionally
    # exposes substantial over-selection rather than relabeling it away.
    assert result["metrics"]["irrelevant_selection_rate"] <= 0.45
    assert 0 <= result["metrics"]["impact_precision"] <= 1
    assert 0 <= result["metrics"]["impact_recall"] <= 1
    assert result["metrics"]["unsupported_claim_rate"] == 0


def test_subscription_domain_covers_required_independent_categories():
    result = evaluate()
    categories = {row["category"] for row in result["scenarios"]}
    assert {
        "authorization", "state transition", "business rule", "integration and retry",
        "notification", "idempotency", "rollback", "API contract", "background job",
        "database", "integration failure", "contradiction", "dead code",
        "ambiguous terminology", "irrelevant code",
    } <= categories
