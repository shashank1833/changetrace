from pathlib import Path

from workers.analysis import AnalysisPipeline

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"
PATCH = """diff --git a/backend/models/order.py b/backend/models/order.py
--- a/backend/models/order.py
+++ b/backend/models/order.py
@@ -7,2 +7,3 @@ class OrderStatus(str, Enum):
     SHIPPED = "SHIPPED"
+    RETURNED = "RETURNED"
     CANCELLED = "CANCELLED"
"""


def test_diff_produces_before_after_delta_and_direct_impact():
    result = AnalysisPipeline().run(
        FIXTURE,
        "Add RETURNED after shipment and allow a refund after inspection.",
        proposed_diff=PATCH,
        repository_id="repo-demo",
    )
    assert result.change_set is not None
    assert result.graph_delta is not None
    assert "STATE:backend/models/order.py:OrderStatus.RETURNED" in result.graph_delta.added_components
    assert any(component.location.file == "backend/models/order.py" for component in result.components)
    assert all(item.repository_id == "repo-demo" for item in result.evidence)
    assert result.decision.status.value in {"GO", "REVIEW", "BLOCK"}
