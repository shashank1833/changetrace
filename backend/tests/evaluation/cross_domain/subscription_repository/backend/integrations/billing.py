import httpx


def cancel_billing(subscription_id):
    return httpx.post("https://billing.example/subscriptions/cancel", json={"id": subscription_id})


def charge_invoice(subscription_id, amount, idempotency_key=None):
    return httpx.post(
        "https://billing.example/invoices",
        json={"id": subscription_id, "amount": amount},
        headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
    )
