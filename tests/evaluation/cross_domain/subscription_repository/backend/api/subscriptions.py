from backend.services.subscription_service import cancel_subscription
from fastapi import APIRouter

router = APIRouter()


@router.post("/subscriptions/{subscription_id}/cancel")
def cancel(subscription_id: int):
    return cancel_subscription(load_subscription(subscription_id), current_account_id())


def load_subscription(subscription_id):
    raise NotImplementedError


def current_account_id():
    return 1
