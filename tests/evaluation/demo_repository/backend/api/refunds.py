from fastapi import APIRouter
from backend.services.refund_service import refund_is_eligible

router = APIRouter()


@router.get("/orders/{order_id}/refund-eligibility")
def get_refund_eligibility(order_id: int):
    order = load_order(order_id)
    return {"eligible": refund_is_eligible(order)}


def load_order(order_id):
    raise NotImplementedError
