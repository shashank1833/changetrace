from backend.integrations.billing import cancel_billing
from backend.models.subscription import SubscriptionStatus


def cancel_subscription(subscription, actor_account_id):
    if subscription.account_id != actor_account_id:
        raise PermissionError("account owner required")
    if subscription.status == SubscriptionStatus.CANCELLED:
        return subscription
    cancel_billing(subscription.id)
    subscription.status = SubscriptionStatus.CANCELLED
    return subscription


def suspend_past_due(subscription):
    if subscription.status != SubscriptionStatus.PAST_DUE:
        raise ValueError("only past due subscriptions may be suspended")
    subscription.status = SubscriptionStatus.SUSPENDED
    return subscription
