def export_usage_period(subscription):
    """Return the subscription usage period label; this does not change billing state."""
    return {"period": subscription.plan}
