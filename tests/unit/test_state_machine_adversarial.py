from pathlib import Path

from services.repository_analysis import RepositoryAnalyzer
from services.state_machines import StateMachineAnalyzer


def discover(tmp_path: Path, source: str):
    (tmp_path / "workflow.py").write_text(source)
    index = RepositoryAnalyzer().scan(tmp_path, "snapshot", "commit")
    return StateMachineAnalyzer().discover(index)


def test_generic_state_model_extracts_supported_transitions(tmp_path: Path):
    machines = discover(
        tmp_path,
        """from enum import Enum
class TicketState(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

def transition(ticket, target):
    allowed = {
        TicketState.OPEN: {TicketState.ASSIGNED},
        TicketState.ASSIGNED: {TicketState.RESOLVED},
        TicketState.RESOLVED: {TicketState.CLOSED},
    }
    return target in allowed[ticket.state]
""",
    )
    ticket = next(machine for machine in machines if machine.entity == "Ticket")
    pairs = {(item.from_state, item.to_state) for item in ticket.transitions}
    assert ("OPEN", "ASSIGNED") in pairs
    assert ("RESOLVED", "CLOSED") in pairs
    assert ("CLOSED", "OPEN") not in pairs


def test_documented_transition_is_not_treated_as_implemented(tmp_path: Path):
    machines = discover(
        tmp_path,
        """from enum import Enum
class AccessState(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REVOKED = "REVOKED"
# Documentation says REVOKED may become APPROVED, but no transition map implements it.
""",
    )
    access = next(machine for machine in machines if machine.entity == "Access")
    assert access.transitions == []
