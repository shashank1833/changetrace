from __future__ import annotations


class FeeService:
    """Calculates processing fees and interchange costs."""

    def calculate_fee(self, amount_cents: int, currency: str) -> int:
        # Standard fee: 2.9% + 30 cents
        base_fee = int(amount_cents * 0.029) + 30
        if currency != "USD":
            # Multi-currency surcharge 1%
            base_fee += int(amount_cents * 0.01)
        return base_fee

    def refund_fee_reversal(self, fee_cents: int) -> int:
        """Fixed interchange fee is non-refundable by network rule."""
        return max(0, fee_cents - 30)
