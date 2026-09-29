from backend.services.billing_service import retry_past_due_payment


def process_billing_event(event):
    # Delivery can be duplicated; event_id is the idempotency key.
    return retry_past_due_payment(event["subscription"], event["amount"], event["event_id"])
