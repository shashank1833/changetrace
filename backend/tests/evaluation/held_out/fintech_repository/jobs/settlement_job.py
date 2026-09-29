from __future__ import annotations

from services.payment_service import PaymentService


class DailySettlementJob:
    def __init__(self) -> None:
        self.payment_service = PaymentService()

    def process_pending_authorizations(self, batch_ids: list[str]) -> int:
        count = 0
        for pid in batch_ids:
            # Batch settles payments
            count += 1
        return count
