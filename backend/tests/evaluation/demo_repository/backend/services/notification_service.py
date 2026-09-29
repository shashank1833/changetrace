def notify_order_status(order):
    if order.status in {"SHIPPED", "CANCELLED"}:
        return {"template": f"order_{order.status.lower()}", "customer_id": order.customer_id}
    return None
