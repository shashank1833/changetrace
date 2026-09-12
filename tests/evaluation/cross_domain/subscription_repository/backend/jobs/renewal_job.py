from backend.integrations.billing import charge_invoice


def renewal_job(subscription, amount):
    if subscription.status == "ACTIVE":
        return charge_invoice(subscription.id, amount)
    return None
