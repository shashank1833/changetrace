def analytics_bucket(order):
    if order.status == "CANCELLED":
        return "lost_revenue"
    if order.status == "SHIPPED":
        return "fulfilled"
    return "open"
