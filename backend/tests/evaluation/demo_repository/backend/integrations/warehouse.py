import httpx


def request_inspection(order_id):
    return httpx.post("https://warehouse.example/inspections", json={"order_id": order_id})


def inspection_succeeded(payload):
    return payload.get("result") == "PASS"
