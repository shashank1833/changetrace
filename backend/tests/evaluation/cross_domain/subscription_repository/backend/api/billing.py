from backend.services.billing_service import retry_past_due_payment
from fastapi import APIRouter

router = APIRouter()


@router.post("/subscriptions/{subscription_id}/retry-payment")
def retry_payment(subscription_id: int, idempotency_key: str):
    return retry_past_due_payment(load_subscription(subscription_id), 100, idempotency_key)


def load_subscription(subscription_id):
    raise NotImplementedError
