from pathlib import Path

import pytest
from changetrace_schemas import ChangeKind

from services.repository_analysis import DiffAnalyzer, DiffParseError, SnapshotService

FIXTURE = Path(__file__).parents[1] / "evaluation" / "demo_repository"
PATCH = """diff --git a/backend/models/order.py b/backend/models/order.py
--- a/backend/models/order.py
+++ b/backend/models/order.py
@@ -7,2 +7,3 @@ class OrderStatus(str, Enum):
     SHIPPED = "SHIPPED"
+    RETURNED = "RETURNED"
     CANCELLED = "CANCELLED"
diff --git a/schema.sql b/schema.sql
--- a/schema.sql
+++ b/schema.sql
@@ -3,1 +3,1 @@
-  status TEXT NOT NULL CHECK (status IN ('CREATED', 'PAID', 'SHIPPED', 'CANCELLED')),
+  status TEXT NOT NULL CHECK (status IN ('CREATED', 'PAID', 'SHIPPED', 'RETURNED', 'CANCELLED')),
"""


def test_parses_files_lines_and_state_values():
    snapshot = SnapshotService().from_local(FIXTURE)
    change_set = DiffAnalyzer().parse(PATCH, snapshot)
    assert len(change_set.files) == 2
    assert change_set.files[0].state_changes[0].value == "RETURNED"
    assert change_set.files[0].state_changes[0].change_kind == ChangeKind.ADDED
    assert change_set.files[1].added_lines[0].new_line == 3


def test_rejects_path_traversal():
    snapshot = SnapshotService().from_local(FIXTURE)
    patch = "diff --git a/../../secret b/../../secret\n--- a/../../secret\n+++ b/../../secret\n"
    with pytest.raises(DiffParseError, match="Unsafe patch path"):
        DiffAnalyzer().parse(patch, snapshot)
