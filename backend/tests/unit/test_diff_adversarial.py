from pathlib import Path

import pytest

from services.repository_analysis import DiffAnalyzer, DiffParseError, SnapshotService


def snapshot(tmp_path: Path):
    (tmp_path / "a.py").write_text("old = 1\n")
    return SnapshotService().from_local(tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "../../secret",
        "/absolute/file.py",
        "dir/../../../escape.py",
        "C:/Windows/secret.txt",
        r"C:\\Windows\\secret.txt",
    ],
)
def test_rejects_unsafe_patch_paths(tmp_path: Path, path: str):
    patch = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    with pytest.raises(DiffParseError):
        DiffAnalyzer().parse(patch, snapshot(tmp_path))


def test_rejects_binary_patch_without_leaking_payload(tmp_path: Path):
    secret = "SUPER-SECRET-BINARY-CONTENT"
    patch = f"diff --git a/a.bin b/a.bin\nGIT binary patch\n{secret}\n"
    with pytest.raises(DiffParseError) as error:
        DiffAnalyzer().parse(patch, snapshot(tmp_path))
    assert secret not in str(error.value)


def test_rejects_duplicate_file_entries(tmp_path: Path):
    patch = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old = 1\n+old = 2\n"
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old = 1\n+old = 3\n"
    )
    with pytest.raises(DiffParseError, match="Duplicate diff file entry"):
        DiffAnalyzer().parse(patch, snapshot(tmp_path))


def test_rejects_oversized_and_nul_content(tmp_path: Path):
    header = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old = 1\n+"
    with pytest.raises(DiffParseError, match="oversized line"):
        DiffAnalyzer().parse(header + "x" * 100_001, snapshot(tmp_path))
    with pytest.raises(DiffParseError, match="Binary patches"):
        DiffAnalyzer().parse(header + "bad\x00data", snapshot(tmp_path))


def test_rejects_patch_without_file_headers(tmp_path: Path):
    with pytest.raises(DiffParseError, match="No git diff file headers"):
        DiffAnalyzer().parse("@@ -1 +1 @@\n-old\n+new\n", snapshot(tmp_path))


def test_parses_added_deleted_and_renamed_files(tmp_path: Path):
    patch = """diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
diff --git a/created.py b/created.py
new file mode 100644
--- /dev/null
+++ b/created.py
@@ -0,0 +1 @@
+created = True
diff --git a/deleted.py b/deleted.py
deleted file mode 100644
--- a/deleted.py
+++ /dev/null
@@ -1 +0,0 @@
-deleted = True
"""
    changes = DiffAnalyzer().parse(patch, snapshot(tmp_path)).files
    assert [change.change_kind.value for change in changes] == ["RENAMED", "ADDED", "DELETED"]
    assert changes[0].old_path == "old.py" and changes[0].new_path == "new.py"
    assert changes[1].added_lines[0].new_line == 1
    assert changes[2].deleted_lines[0].old_line == 1
