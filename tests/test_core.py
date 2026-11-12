from datetime import datetime

from tl_uurtjes.core import (
    entry_ending_at,
    parse_duration,
    parse_entries,
    parse_tasks,
    pending_slots,
    recent_task_ids,
)

TASKS = """14 assignable task(s):

| Project | Task | Remaining | api_id |
|---|---|---|---|
| 324_010 SynCore | M5: Software development | 92h30 | PTFCTE34CEB1EST |
| INT_018 Internal costs 2026 | *Remaining Activities | unlimited | PTE6G1GDGEB8VPJ |
"""

ENTRIES = """3 time entries:

- 2026-11-11 10:00 | Stijn Vergouwen | 7h | 324_010 SynCore / M5: Software development (task api_id: PTFCTE34CEB1EST)  (api_id: ACFXTUK4A7N8QPX)
- 2026-11-11 09:00 | Stijn Vergouwen | 1h | INT_018 Internal costs 2026 / *Support on other project (task api_id: PT38C95HVB14YNT) — Inschatting Dual Screen  (api_id: ACJDP69ZM7YPDDX)
- 2026-11-04 12:30 | Stijn Vergouwen | 4h30 | 503_004 HomeClinic / System control SW (task api_id: PTKWQNKXQK5ST9U)  (api_id: ACB3K3NJUN6WM4K) [locked: timesheet submitted (FINAL)]
"""


def test_parse_tasks():
    tasks = parse_tasks(TASKS)
    assert [t.id for t in tasks] == ["PTFCTE34CEB1EST", "PTE6G1GDGEB8VPJ"]
    assert tasks[0].project == "324_010 SynCore"
    assert tasks[1].name == "*Remaining Activities"


def test_parse_duration():
    assert parse_duration("7h") == 420
    assert parse_duration("0h30") == 30
    assert parse_duration("4h30") == 270


def test_parse_entries():
    e = parse_entries(ENTRIES)
    assert len(e) == 3
    assert e[0].start == datetime(2026, 11, 11, 10) and e[0].minutes == 420
    assert e[0].task_id == "PTFCTE34CEB1EST" and e[0].description == "" and not e[0].locked
    assert e[1].description == "Inschatting Dual Screen"
    assert e[2].locked


def test_pending_slots_skips_covered_and_skipped():
    entries = parse_entries(ENTRIES)
    now = datetime(2026, 11, 11, 18, 0)
    # 09:00-17:00 is covered by the two entries; 17:00-18:00 is still open.
    assert pending_slots(now, entries, set()) == [datetime(2026, 11, 11, 17)]
    # Without entries every hour that has ended is pending, minus skipped ones.
    now = datetime(2026, 11, 11, 12, 5)
    skipped = {datetime(2026, 11, 11, 10)}
    assert pending_slots(now, [], skipped) == [datetime(2026, 11, 11, 9), datetime(2026, 11, 11, 11)]


def test_no_slots_in_weekend():
    assert pending_slots(datetime(2026, 11, 14, 18), [], set()) == []


def test_entry_ending_at_and_recent():
    entries = parse_entries(ENTRIES)
    assert entry_ending_at(datetime(2026, 11, 11, 10), entries).id == "ACJDP69ZM7YPDDX"
    assert entry_ending_at(datetime(2026, 11, 11, 13), entries) is None
    assert recent_task_ids(entries) == ["PTFCTE34CEB1EST", "PT38C95HVB14YNT", "PTKWQNKXQK5ST9U"]
