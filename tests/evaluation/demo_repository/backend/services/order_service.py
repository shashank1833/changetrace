from backend.models.order import OrderStatus
from backend.services.refund_service import process_refund
from backend.integrations.warehouse import request_inspection


def change_status(order, new_status, actor_id):
    if order.customer_id != actor_id:
        raise PermissionError("customer may only modify owned order")
    allowed = {
        OrderStatus.CREATED: {OrderStatus.PAID, OrderStatus.CANCELLED},
        OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
        OrderStatus.SHIPPED: set(),
    }
    if new_status not in allowed.get(order.status, set()):
        raise ValueError("invalid order status transition")
    order.status = new_status
    return order
