SQL = "SELECT id, account_id, status, plan FROM subscriptions WHERE id = :id"


def save_subscription(subscription):
    return "UPDATE subscriptions SET status = :status WHERE id = :id"
