def release_inventory(order):
    if order.status == "CANCELLED":
        return {"released": True, "order_id": order.id}
    return {"released": False, "order_id": order.id}


def restock_returned_item(order, inspection):
    if inspection == "PASS":
        return {"restocked": True, "order_id": order.id}
    return {"restocked": False, "order_id": order.id}
