from backend.models.order import OrderStatus
from backend.services.payment_service import reverse_payment


def process_refund(order):
    # Hidden rule: refunds only recognize cancellation, not post-shipment returns.
    if order.status == OrderStatus.CANCELLED:
        return reverse_payment(order.id)
    return None


def refund_is_eligible(order):
    return order.status == OrderStatus.CANCELLED
