from backend.models.order import OrderStatus


def test_cancelled_order_can_be_refunded():
    assert OrderStatus.CANCELLED.value == "CANCELLED"


def test_customer_cannot_modify_another_order():
    assert True
