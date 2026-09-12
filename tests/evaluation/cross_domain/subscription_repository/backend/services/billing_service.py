from backend.integrations.billing import charge_invoice
from backend.models.subscription import SubscriptionStatus


def retry_past_due_payment(subscription, amount, idempotency_key):
    if subscription.status != SubscriptionStatus.PAST_DUE:
        raise ValueError("only past-due subscriptions can retry payment")
    return charge_invoice(subscription.id, amount, idempotency_key=idempotency_key)


def rollback_failed_payment(subscription):
    subscription.status = SubscriptionStatus.PAST_DUE
    return subscription


def pause_subscription(subscription):
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise ValueError("only active subscriptions can be paused")
    subscription.status = "PAUSED"
    return subscription
