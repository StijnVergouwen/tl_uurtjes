from datetime import datetime

from tl_uurtjes.core import (
    WorkHours,
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
| 100_001 Example Project | Software development | 92h30 | TASK00000000001 |
| INT_001 Internal costs | *Remaining Activities | unlimited | TASK00000000002 |
"""

ENTRIES = """3 time entries:

- 2026-11-11 10:00 | Jan Jansen | 7h | 100_001 Example Project / Software development (task api_id: TASK00000000001)  (api_id: ENTRY0000000001)
- 2026-11-11 09:00 | Jan Jansen | 1h | INT_001 Internal costs / *Support on other project (task api_id: TASK00000000003) — Voorbeeld omschrijving  (api_id: ENTRY0000000002)
- 2026-11-04 12:30 | Jan Jansen | 4h30 | 200_002 Demo Client / Firmware (task api_id: TASK00000000004)  (api_id: ENTRY0000000003) [locked: timesheet submitted (FINAL)]
"""


def test_parse_tasks():
    tasks = parse_tasks(TASKS)
    assert [t.id for t in tasks] == ["TASK00000000001", "TASK00000000002"]
    assert tasks[0].project == "100_001 Example Project"
    assert tasks[1].name == "*Remaining Activities"


def test_parse_duration():
    assert parse_duration("7h") == 420
    assert parse_duration("0h30") == 30
    assert parse_duration("4h30") == 270


def test_parse_entries():
    e = parse_entries(ENTRIES)
    assert len(e) == 3
    assert e[0].start == datetime(2026, 11, 11, 10) and e[0].minutes == 420
    assert e[0].task_id == "TASK00000000001" and e[0].description == "" and not e[0].locked
    assert e[1].description == "Voorbeeld omschrijving"
    assert e[2].locked


def test_pending_slots_skips_covered_and_skipped():
    entries = parse_entries(ENTRIES)
    now = datetime(2026, 11, 11, 18, 0)
    # 09:00-17:00 is covered by the two entries; 17:00-18:00 is still open.
    assert pending_slots(now, entries, set(), WorkHours()) == [datetime(2026, 11, 11, 17)]
    # Without entries every hour that has ended is pending, minus skipped ones.
    now = datetime(2026, 11, 11, 12, 5)
    skipped = {datetime(2026, 11, 11, 10)}
    assert pending_slots(now, [], skipped, WorkHours()) == [datetime(2026, 11, 11, 9), datetime(2026, 11, 11, 11)]


def test_no_slots_in_weekend():
    assert pending_slots(datetime(2026, 11, 14, 18), [], set(), WorkHours()) == []


def test_entry_ending_at_and_recent():
    entries = parse_entries(ENTRIES)
    assert entry_ending_at(datetime(2026, 11, 11, 10), entries).id == "ENTRY0000000002"
    assert entry_ending_at(datetime(2026, 11, 11, 13), entries) is None
    assert recent_task_ids(entries) == ["TASK00000000001", "TASK00000000003", "TASK00000000004"]


def test_custom_work_hours():
    hours = WorkHours(start_hour=8, end_hour=12, workdays=(0, 1, 3))  # Mon, Tue, Thu
    now = datetime(2026, 11, 12, 15, 0)  # Thursday afternoon
    assert pending_slots(now, [], set(), hours) == [datetime(2026, 11, 12, h) for h in (8, 9, 10, 11)]
    assert pending_slots(datetime(2026, 11, 11, 15), [], set(), hours) == []  # Wednesday is off
    # The hourly timer only pops up at the end of a work hour (9:00 ... 12:00) on a workday.
    assert [h for h in range(24) if hours.is_reminder_time(datetime(2026, 11, 12, h))] == [9, 10, 11, 12]
    assert not hours.is_reminder_time(datetime(2026, 11, 11, 10))  # Wednesday


def test_parse_workdays():
    import pytest

    from tl_uurtjes.core import parse_workdays

    assert parse_workdays("1-5") == (0, 1, 2, 3, 4)
    assert parse_workdays("1-3, 5") == (0, 1, 2, 4)
    for bad in ("0", "8", "5-1", ""):
        with pytest.raises(ValueError):
            parse_workdays(bad)
    with pytest.raises(ValueError):
        WorkHours(start_hour=17, end_hour=9)


def test_work_hours_roundtrip(tmp_path):
    from tl_uurtjes.core import load_work_hours, save_work_hours

    path = tmp_path / "settings.json"
    assert load_work_hours(path) == WorkHours()  # defaults when not set up yet
    save_work_hours(WorkHours(8, 17, (0, 1, 2, 3)), path)
    assert load_work_hours(path) == WorkHours(8, 17, (0, 1, 2, 3))
