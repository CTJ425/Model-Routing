import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "route", "scripts"))
from roll_records import roll_records, find_entries


def test_find_entries_progress():
    content = """# Progress

Header text here.

---

## 📅 Log: 2026-08-24 09:00:00 CST (first)

- Changed: a.py
- Verify: PASS

---

## 📅 Log: 2026-08-23 09:00:00 CST (second)

- Changed: b.py
"""
    header, entries = find_entries(content, r"^(?:## 📅 Log:|### )")
    assert "# Progress" in header
    assert len(entries) == 2
    assert "Log: 2026-08-24 09:00:00 CST (first)" in entries[0]["heading"]
    assert "Log: 2026-08-23 09:00:00 CST (second)" in entries[1]["heading"]


def test_roll_records_noop_when_under_keep(tmp_path):
    hot = tmp_path / "PROGRESS.md"
    arch = tmp_path / "PROGRESS_ARCHIVE.md"
    hot.write_text("""# Progress

Header

---

## 📅 Log: 2026-08-24 (1)

Content 1
""")
    rc = roll_records(str(hot), str(arch), keep=2)
    assert rc == 0
    assert not arch.exists()
    assert "Content 1" in hot.read_text()


def test_roll_records_prepends_to_archive(tmp_path):
    hot = tmp_path / "PROGRESS.md"
    arch = tmp_path / "PROGRESS_ARCHIVE.md"
    arch.write_text("""# Progress archive

Older entries.
""")

    hot.write_text("""# Progress

Header text.

---

## 📅 Log: 2026-08-24 (newest)

- Changed: x.py

---

## 📅 Log: 2026-08-23 (middle)

- Changed: y.py

---

## 📅 Log: 2026-08-22 (oldest)

- Changed: z.py
""")

    rc = roll_records(str(hot), str(arch), keep=2)
    assert rc == 0

    hot_text = hot.read_text()
    arch_text = arch.read_text()

    # Hot file keeps newest 2
    assert "2026-08-24 (newest)" in hot_text
    assert "2026-08-23 (middle)" in hot_text
    assert "2026-08-22 (oldest)" not in hot_text

    # Archive has the oldest entry
    assert "2026-08-22 (oldest)" in arch_text
    assert "# Progress archive" in arch_text


def test_roll_records_multiple_overflow_prepended_order(tmp_path):
    hot = tmp_path / "PROGRESS.md"
    arch = tmp_path / "PROGRESS_ARCHIVE.md"
    arch.write_text("""# Progress archive

Older entries.

---

## 📅 Log: 2026-08-20 (ancient)

- Changed: ancient.py
""")

    hot.write_text("""# Progress

Header text.

---

## 📅 Log: 2026-08-24 (1)

- Changed: 1.py

---

## 📅 Log: 2026-08-23 (2)

- Changed: 2.py

---

## 📅 Log: 2026-08-22 (3)

- Changed: 3.py
""")

    # keep=1 -> 2 and 3 should roll to archive, prepended before ancient
    rc = roll_records(str(hot), str(arch), keep=1)
    assert rc == 0

    hot_text = hot.read_text()
    arch_text = arch.read_text()

    assert "2026-08-24 (1)" in hot_text
    assert "2026-08-23 (2)" not in hot_text
    assert "2026-08-22 (3)" not in hot_text

    # Check archive ordering: (2), then (3), then (ancient)
    pos2 = arch_text.find("2026-08-23 (2)")
    pos3 = arch_text.find("2026-08-22 (3)")
    pos_anc = arch_text.find("2026-08-20 (ancient)")
    assert pos2 != -1 and pos3 != -1 and pos_anc != -1
    assert pos2 < pos3 < pos_anc


def test_roll_records_task_headings(tmp_path):
    hot = tmp_path / "TASK.md"
    arch = tmp_path / "TASK_ARCHIVE.md"

    hot.write_text("""# Tasks

Header.

## 📋 Active Tasks

### Task 1: open task
- Status: IN PROGRESS

### Task 2: done task
- Status: DONE
""")

    arch.write_text("""# Tasks archive

Header.
""")

    rc = roll_records(str(hot), str(arch), keep=1, heading_pattern=r"^### ")
    assert rc == 0

    assert "### Task 1: open task" in hot.read_text()
    assert "### Task 2: done task" not in hot.read_text()
    assert "### Task 2: done task" in arch.read_text()
