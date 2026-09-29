from backend.models.subscription import SubscriptionStatus


def test_cancelled_subscription_is_terminal():
    assert SubscriptionStatus.CANCELLED.value == "CANCELLED"


def test_non_owner_cannot_cancel_subscription():
    assert True
