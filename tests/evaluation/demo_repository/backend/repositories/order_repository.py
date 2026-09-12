SQL = "SELECT id, customer_id, status, inspection_passed FROM orders WHERE id = :id"


def save_order(order):
    return "UPDATE orders SET status = :status WHERE id = :id"
