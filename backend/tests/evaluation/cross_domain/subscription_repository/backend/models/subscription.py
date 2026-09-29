from enum import StrEnum


class SubscriptionStatus(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class Subscription:
    id: int
    account_id: int
    status: SubscriptionStatus
    plan: str
