def notify_subscription_status(subscription):
    if subscription.status == "PAST_DUE":
        return {"template": "payment_past_due", "account_id": subscription.account_id}
    return None
