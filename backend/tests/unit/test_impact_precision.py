from pathlib import Path

from changetrace_schemas import ImpactStatus

from services.changes import ChangeInterpreter
from services.graph import RepositoryGraph
from services.impact import ImpactEngine
from services.repository_analysis import RepositoryAnalyzer


def analyze(root: Path, request: str):
    index = RepositoryAnalyzer().scan(root, "snapshot", "commit")
    intent = ChangeInterpreter().interpret(request)
    return ImpactEngine().discover(index, RepositoryGraph(index), intent)[0]


def test_return_keyword_is_not_a_business_return_match(tmp_path):
    (tmp_path / "refunds.py").write_text("def refund_order(order):\n    return order\n")
    (tmp_path / "descriptions.py").write_text("def refund_description():\n    return 'text'\n")
    (tmp_path / "unrelated.py").write_text("def calculate_total():\n    return 42\n")

    components = analyze(tmp_path, "Change refund order eligibility after inspection")
    by_file = {component.location.file: component for component in components}

    assert by_file["refunds.py"].impact_status == ImpactStatus.CANDIDATE
    assert by_file["descriptions.py"].impact_status == ImpactStatus.CANDIDATE
    assert "unrelated.py" not in by_file


def test_valid_direct_dependency_is_likely_with_explainable_causal_path(tmp_path):
    (tmp_path / "gateway.py").write_text("def inspect_package(package):\n    return package.approved\n")
    (tmp_path / "returns.py").write_text(
        "from gateway import inspect_package\n\n"
        "def approve_return(package):\n"
        "    return inspect_package(package)\n"
    )

    components = analyze(tmp_path, "Inspect a package before approve return package")
    direct = next(item for item in components if item.name == "inspect_package")

    assert direct.impact_status == ImpactStatus.LIKELY
    assert any(part.startswith("RELATIONSHIP") for part in direct.reasoning_path)
    assert any(part.startswith("EVIDENCE") for part in direct.reasoning_path)


def test_indirect_dependency_is_never_confirmed_without_a_changed_artifact(tmp_path):
    (tmp_path / "gateway.py").write_text("def inspect_package(package):\n    return package.approved\n")
    (tmp_path / "returns.py").write_text(
        "from gateway import inspect_package\n\n"
        "def approve_return(package):\n"
        "    return inspect_package(package)\n"
    )
    (tmp_path / "report.py").write_text(
        "from returns import approve_return\n\n"
        "def inspection_return_report(package):\n"
        "    return approve_return(package)\n"
    )

    components = analyze(tmp_path, "Inspect a package before approve return package")
    report = next(item for item in components if item.name == "inspection_return_report")

    assert report.impact_status in {ImpactStatus.CANDIDATE, ImpactStatus.LIKELY}
    assert report.impact_status != ImpactStatus.CONFIRMED


def test_overloaded_return_verb_does_not_promote_business_return_flow(tmp_path):
    (tmp_path / "warehouse.py").write_text("def shipment_label():\n    return 'label'\n")
    (tmp_path / "returns.py").write_text(
        "def handle_return(order, inspection):\n"
        "    order.status = 'RETURNED'\n"
        "    return inspection\n"
    )

    components = analyze(tmp_path, "Return the warehouse shipment label from the inspection endpoint")
    return_flow = [item for item in components if item.location.file == "returns.py"]

    assert all(item.impact_status == ImpactStatus.CANDIDATE for item in return_flow)


def test_unrelated_shared_nouns_without_relationship_remain_candidates(tmp_path):
    (tmp_path / "notifications.py").write_text(
        "def notify_customer(order):\n"
        "    return order.status == 'SHIPPED'\n"
    )
    (tmp_path / "ownership.py").write_text(
        "def authorize_customer_return(order, customer):\n"
        "    return order.customer_id == customer.id\n"
    )

    components = analyze(tmp_path, "Only the customer who owns a shipped order may request its return")
    notification = next(item for item in components if item.name == "notify_customer")

    assert notification.impact_status != ImpactStatus.CONFIRMED
    assert all("CALLS" not in step and "IMPORTS" not in step for step in notification.reasoning_path)


def test_explicit_predecessor_state_reference_is_likely_for_transition_request(tmp_path):
    (tmp_path / "order.py").write_text(
        "from enum import Enum\n\n"
        "class OrderStatus(Enum):\n"
        "    SHIPPED = 'SHIPPED'\n"
        "    CANCELLED = 'CANCELLED'\n"
    )

    components = analyze(tmp_path, "Cancel a shipped order")
    shipped = next(item for item in components if item.name == "OrderStatus.SHIPPED")

    assert shipped.impact_status == ImpactStatus.LIKELY
    assert shipped.impact_status != ImpactStatus.CONFIRMED


def test_non_transition_state_word_does_not_promote_unrelated_enum(tmp_path):
    (tmp_path / "order.py").write_text(
        "from enum import Enum\n\n"
        "class OrderStatus(Enum):\n"
        "    SHIPPED = 'SHIPPED'\n"
    )

    components = analyze(tmp_path, "Only the customer who owns a shipped order may request its return")
    shipped = next(item for item in components if item.name == "OrderStatus.SHIPPED")

    assert shipped.impact_status == ImpactStatus.CANDIDATE


def test_business_rule_in_affected_symbol_remains_likely(tmp_path):
    (tmp_path / "orders.py").write_text(
        "def cancel_paid_order(order):\n"
        "    if order.status == 'PAID':\n"
        "        raise ValueError('paid cancellation blocked')\n"
    )

    components = analyze(tmp_path, "Prevent cancellation of PAID orders")
    rule = next(item for item in components if item.type.value == "BUSINESS_RULE")

    assert rule.impact_status == ImpactStatus.LIKELY


def test_ubiquitous_domain_term_does_not_promote_unqualified_component(tmp_path):
    (tmp_path / "billing.py").write_text(
        "def retry_subscription_payment(subscription):\n"
        "    return subscription.payment\n"
    )
    for number in range(4):
        (tmp_path / f"subscription_{number}.py").write_text(
            f"def inspect_subscription_{number}(subscription):\n"
            "    return subscription.status\n"
        )
    (tmp_path / "other.py").write_text("def health_check():\n    return True\n")

    components = analyze(tmp_path, "Retry a subscription payment")
    retry = next(item for item in components if item.name == "retry_subscription_payment")
    unrelated = next(item for item in components if item.name == "inspect_subscription_0")

    assert retry.impact_status == ImpactStatus.LIKELY
    assert unrelated.impact_status == ImpactStatus.CANDIDATE


def test_state_importer_must_reference_requested_state_in_dense_domain(tmp_path):
    (tmp_path / "subscription.py").write_text(
        "from enum import Enum\n\n"
        "class SubscriptionStatus(Enum):\n"
        "    ACTIVE = 'ACTIVE'\n"
    )
    (tmp_path / "pause_subscription.py").write_text(
        "from subscription import SubscriptionStatus\n\n"
        "def pause_subscription(subscription):\n"
        "    return subscription.status == SubscriptionStatus.ACTIVE\n"
    )
    for number in range(3):
        (tmp_path / f"subscription_user_{number}.py").write_text(
            "from subscription import SubscriptionStatus\n\n"
            f"def inspect_subscription_{number}(subscription):\n"
            "    return subscription.status\n"
        )
    (tmp_path / "other.py").write_text("def health_check():\n    return True\n")

    components = analyze(tmp_path, "Pause an ACTIVE subscription")
    likely_files = {
        item.location.file
        for item in components
        if item.impact_status == ImpactStatus.LIKELY
    }

    assert "pause_subscription.py" in likely_files
    assert "subscription_user_0.py" not in likely_files


def test_adding_disconnected_file_does_not_change_likely_impacts(tmp_path):
    (tmp_path / "service.py").write_text("def authorize_subscription(user):\n    return user.active\n")
    before = analyze(tmp_path, "Require subscription authorization for active users")
    (tmp_path / "other.py").write_text("def unrelated():\n    return 'authorization documentation'\n")
    after = analyze(tmp_path, "Require subscription authorization for active users")

    def likely(items):
        return {
            (item.location.file, item.name)
            for item in items
            if item.impact_status in {ImpactStatus.LIKELY, ImpactStatus.CONFIRMED}
        }

    assert likely(before) == likely(after)
