from fastapi import APIRouter
from backend.services.order_service import change_status

router = APIRouter()


@router.post("/orders/{order_id}/status")
def update_order_status(order_id: int, status: str):
    return change_status(load_order(order_id), status, current_user_id())


def load_order(order_id):
    raise NotImplementedError


def current_user_id():
    return 1
