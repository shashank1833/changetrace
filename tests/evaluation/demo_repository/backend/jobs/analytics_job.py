from backend.services.analytics_service import analytics_bucket


def analytics_job(order):
    return {"order_id": order.id, "bucket": analytics_bucket(order)}
