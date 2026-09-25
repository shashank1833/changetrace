from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PaymentStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    AUTHORIZED = "AUTHORIZED"
    SETTLING = "SETTLING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"


@dataclass
class PaymentRecord:
    payment_id: str
    merchant_id: str
    amount_cents: int
    currency: str
    status: PaymentStatus
    created_at: str
