from __future__ import annotations

from models.payment import PaymentRecord, PaymentStatus
from services.fee_service import FeeService
from services.currency_service import CurrencyService

VALID_PAYMENT_TRANSITIONS: dict[str, list[str]] = {
    "INITIALIZED": ["AUTHORIZED", "FAILED"],
    "AUTHORIZED": ["SETTLING", "FAILED"],
    "SETTLING": ["SETTLED", "FAILED"],
    "SETTLED": ["REFUNDED", "DISPUTED"],
    "REFUNDED": [],
    "FAILED": [],
    "DISPUTED": ["SETTLED", "REFUNDED"],
}


class PaymentService:
    def __init__(self) -> None:
        self.fee_service = FeeService()
        self.currency_service = CurrencyService()

    def authorize(self, record: PaymentRecord) -> PaymentRecord:
        if record.status != PaymentStatus.INITIALIZED:
            raise ValueError(f"Cannot authorize from {record.status}")
        # Transition: INITIALIZED -> AUTHORIZED
        record.status = PaymentStatus.AUTHORIZED
        return record

    def settle(self, record: PaymentRecord) -> PaymentRecord:
        if record.status != PaymentStatus.AUTHORIZED:
            raise ValueError(f"Cannot settle from {record.status}")
        record.status = PaymentStatus.SETTLING
        fee = self.fee_service.calculate_fee(record.amount_cents, record.currency)
        record.status = PaymentStatus.SETTLED
        return record

    def refund(self, record: PaymentRecord, reason: str = "") -> PaymentRecord:
        if record.status != PaymentStatus.SETTLED:
            raise ValueError("Only SETTLED payments can be refunded")
        record.status = PaymentStatus.REFUNDED
        return record
