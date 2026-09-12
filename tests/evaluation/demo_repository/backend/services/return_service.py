from backend.integrations.warehouse import inspection_succeeded
from backend.services.refund_service import process_refund


def handle_return(order, inspection_payload):
    if order.status != "SHIPPED":
        raise ValueError("only shipped orders can be returned")
    if not inspection_succeeded(inspection_payload):
        return {"status": "INSPECTION_FAILED"}
    order.status = "RETURNED"
    process_refund(order)
    return {"status": "RETURNED"}


def rollback_return(order):
    order.status = "SHIPPED"
    return order
