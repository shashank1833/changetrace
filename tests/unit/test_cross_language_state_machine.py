from pathlib import Path

from services.repository_analysis import RepositoryAnalyzer
from services.state_machines import StateMachineAnalyzer

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"


def test_cross_language_state_machine_and_side_effects():
    index = RepositoryAnalyzer().scan(FIXTURE, "snap-ts-state", "commit-ts-state")
    machines = StateMachineAnalyzer().discover(index)

    order = next(machine for machine in machines if machine.entity == "Order")
    # Verified cross-language states merged from backend Python and frontend TS
    assert {"CREATED", "PAID", "SHIPPED", "CANCELLED"} <= set(order.states)

    # Check side effects on transition
    paid_to_shipped = next(
        item for item in order.transitions if item.from_state == "PAID" and item.to_state == "SHIPPED"
    )
    assert paid_to_shipped is not None
    assert "state_assignment: order.status" in paid_to_shipped.side_effects

    # Check transition-test mapping
    assert hasattr(paid_to_shipped, "tests")
    assert isinstance(paid_to_shipped.tests, list)


def test_typescript_state_machine_extraction(tmp_path: Path):
    ts_file = tmp_path / "frontend" / "paymentStatus.ts"
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(
        """export type PaymentStatus = 'INITIAL' | 'PROCESSING' | 'COMPLETED' | 'FAILED'

export function isFailed(status: PaymentStatus): boolean {
    return status === 'FAILED'
}
"""
    )
    test_file = tmp_path / "frontend" / "test_payment.ts"
    test_file.write_text(
        """describe('payment', () => {
    it('handles FAILED status', () => {
        expect(isFailed('FAILED')).toBe(true)
    })
})
"""
    )
    index = RepositoryAnalyzer().scan(tmp_path, "snap-ts", "commit-ts")
    machines = StateMachineAnalyzer().discover(index)
    payment = next(m for m in machines if m.entity == "Payment")
    assert {"INITIAL", "PROCESSING", "COMPLETED", "FAILED"} <= set(payment.states)
    failed_transition = next(t for t in payment.transitions if t.from_state == "FAILED")
    assert failed_transition.handler == "isFailed"
