from models.payment import PaymentRecord, PaymentStatus
from services.payment_service import PaymentService


def test_payment_authorization():
    service = PaymentService()
    record = PaymentRecord("p1", "m1", 5000, "USD", PaymentStatus.INITIALIZED, "2026-09-01T00:00:00Z")
    service.authorize(record)
    assert record.status == PaymentStatus.AUTHORIZED


def test_payment_settlement():
    service = PaymentService()
    record = PaymentRecord("p1", "m1", 5000, "USD", PaymentStatus.AUTHORIZED, "2026-09-01T00:00:00Z")
    service.settle(record)
    assert record.status == PaymentStatus.SETTLED
