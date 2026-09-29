import requests


def reverse_payment(order_id):
    return requests.post("https://payments.example/refunds", json={"order_id": order_id}, timeout=3)
