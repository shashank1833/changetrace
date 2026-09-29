from pathlib import Path

from services.repository_analysis import RepositoryAnalyzer
from services.state_machines import StateMachineAnalyzer

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_discovers_states_and_transitions():
    index = RepositoryAnalyzer().scan(FIXTURE, "snap-state", "commit-state")
    machines = StateMachineAnalyzer().discover(index)
    order = next(machine for machine in machines if machine.entity == "Order")
    assert {"CREATED", "PAID", "SHIPPED", "CANCELLED"} <= set(order.states)
    assert any(item.from_state == "PAID" and item.to_state == "SHIPPED" for item in order.transitions)
    assert all(item.evidence_ids for item in order.transitions)
