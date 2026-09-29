from __future__ import annotations

from models.payment import PaymentRecord, PaymentStatus
from services.payment_service import PaymentService


class PaymentApi:
    def __init__(self) -> None:
        self.service = PaymentService()

    def post_payment(self, payment_id: str, merchant_id: str, amount_cents: int, currency: str) -> dict:
        record = PaymentRecord(
            payment_id=payment_id,
            merchant_id=merchant_id,
            amount_cents=amount_cents,
            currency=currency,
            status=PaymentStatus.INITIALIZED,
            created_at="2026-09-01T00:00:00Z",
        )
        authorized = self.service.authorize(record)
        return {"status": authorized.status.value, "payment_id": authorized.payment_id}

    def post_refund(self, record: PaymentRecord, reason: str = "") -> dict:
        refunded = self.service.refund(record, reason)
        return {"status": refunded.status.value, "payment_id": refunded.payment_id}
