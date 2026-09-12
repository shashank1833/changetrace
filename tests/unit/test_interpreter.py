from services.changes import ChangeInterpreter


def test_interprets_returned_order_request():
    intent = ChangeInterpreter().interpret(
        "Add RETURNED as an order state after shipment and allow refunds after successful warehouse inspection."
    )
    assert intent.states_added == ["RETURNED"]
    assert {"order", "refund", "warehouse", "inspection"} <= set(intent.entities)
    assert intent.constraints
