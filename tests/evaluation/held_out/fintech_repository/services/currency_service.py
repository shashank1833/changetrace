from __future__ import annotations


class CurrencyService:
    SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD"}

    def validate_currency(self, currency: str) -> bool:
        return currency.upper() in self.SUPPORTED_CURRENCIES

    def get_fx_rate(self, from_currency: str, to_currency: str) -> float:
        if from_currency == to_currency:
            return 1.0
        rates = {("EUR", "USD"): 1.08, ("GBP", "USD"): 1.28, ("JPY", "USD"): 0.0067}
        return rates.get((from_currency, to_currency), 1.0)
