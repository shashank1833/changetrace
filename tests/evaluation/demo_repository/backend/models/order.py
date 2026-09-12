from enum import Enum


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


class Order:
    id: int
    customer_id: int
    status: OrderStatus
    inspection_passed: bool
