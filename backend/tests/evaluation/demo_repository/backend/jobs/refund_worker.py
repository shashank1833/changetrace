from backend.services.refund_service import process_refund


def refund_worker(event):
    # Duplicate events can invoke this path more than once; no idempotency key exists.
    if event["status"] == "CANCELLED":
        return process_refund(event["order"])
