"""Pure logic: parsing Orbit tool output and working out which hours still need logging."""

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "tl_uurtjes"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
STATE_FILE = Path.home() / ".local" / "state" / "tl_uurtjes" / "skipped.json"
LAST_REMINDER_FILE = STATE_FILE.with_name("last_reminder.json")

# TL_UURTJES_NOW="2026-11-12 13:05" fakes the clock and TL_UURTJES_DRY_RUN=1 skips writes, for testing.
FAKE_NOW = os.environ.get("TL_UURTJES_NOW")
DRY_RUN = os.environ.get("TL_UURTJES_DRY_RUN") == "1"


def now() -> datetime:
    return datetime.fromisoformat(FAKE_NOW) if FAKE_NOW else datetime.now()


def at_hour(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour))


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    """Writes via a temp file + rename, so an interrupted save never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")  # unique per process: runs may overlap
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


class SettingsError(Exception):
    pass


@dataclass(frozen=True)
class WorkHours:
    """Personal working hours; set once with `tl-uurtjes setup`."""

    start_hour: int = 9
    end_hour: int = 18
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # 0 = Monday

    def __post_init__(self):
        if not 0 <= self.start_hour < self.end_hour <= 23:
            raise ValueError(f"working hours must satisfy 0 <= start < end <= 23, got {self.start_hour}-{self.end_hour}")
        if not self.workdays or any(d not in range(7) for d in self.workdays):
            raise ValueError(f"invalid workdays: {self.workdays}")

    def should_remind(self, now: datetime, last_reminder: datetime | None) -> bool:
        """Pop up when a work hour has ended since the last popup.

        That covers the end of every work hour, and also a single catch-up after a missed one (laptop
        asleep at 18:00 -> one popup on wake, then quiet for the evening).
        """
        if now.weekday() not in self.workdays or now.hour <= self.start_hour:
            return False
        latest_end = at_hour(now.date(), min(now.hour, self.end_hour))
        return last_reminder is None or last_reminder < latest_end


def parse_hour(text: str) -> int:
    """'8', '08', '8:00', '8u', '17h' -> the hour; whole hours only."""
    m = re.fullmatch(r"(\d{1,2})(?::00|[uh])?", text.strip().lower())
    if not m or int(m[1]) > 23:
        raise ValueError(f"{text!r} is not a whole hour; use e.g. 8 or 17 (half hours are not supported)")
    return int(m[1])


def parse_workdays(text: str) -> tuple[int, ...]:
    """'1-5' -> Mon..Fri, '1,2,4' -> Mon,Tue,Thu; 1 = Monday, 7 = Sunday."""
    days: set[int] = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d)(?:-(\d))?", part)
        if not m or not 1 <= int(m[1]) <= int(m[2] or m[1]) <= 7:
            raise ValueError(f"invalid workdays {part!r}: use numbers, 1 = Monday ... 7 = Sunday, e.g. 1-5 or 1-3,5")
        days.update(range(int(m[1]) - 1, int(m[2] or m[1])))
    if not days:
        raise ValueError("enter at least one workday, e.g. 1-5")
    return tuple(sorted(days))


def load_work_hours(path: Path = SETTINGS_FILE) -> WorkHours:
    """Your saved hours, or the defaults when `setup` hasn't been run; SettingsError if the file is broken."""
    try:
        raw = read_json(path, None)
        if raw is None:
            return WorkHours()
        return WorkHours(int(raw["start_hour"]), int(raw["end_hour"]), tuple(int(d) for d in raw["workdays"]))
    except (KeyError, TypeError, ValueError) as e:  # includes invalid JSON
        raise SettingsError(f"{path} is invalid ({e}).\nRun `uv run tl-uurtjes setup` to fix it.") from e


def save_work_hours(hours: WorkHours, path: Path = SETTINGS_FILE) -> None:
    write_json(path, asdict(hours))


@dataclass(frozen=True)
class Task:
    id: str
    project: str
    name: str
    remaining: str

    @property
    def label(self) -> str:
        return f"{self.project}  ›  {self.name}"


@dataclass(frozen=True)
class Entry:
    id: str
    start: datetime
    minutes: int
    task_id: str | None
    description: str
    locked: bool

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)


def parse_tasks(text: str) -> list[Task]:
    """Parses the markdown table returned by ListMyTasks."""
    tasks = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"[A-Z0-9]{15}", cells[3]):
            tasks.append(Task(id=cells[3], project=cells[0], name=cells[1], remaining=cells[2]))
    return tasks


def parse_duration(text: str) -> int:
    """'7h' -> 420, '0h30' -> 30, '4h30' -> 270."""
    m = re.fullmatch(r"(\d+)h(\d+)?", text.strip())
    if not m:
        raise ValueError(f"unknown duration: {text!r}")
    return int(m[1]) * 60 + int(m[2] or 0)


_ENTRY_RE = re.compile(
    r"^- (?P<start>\d{4}-\d\d-\d\d \d\d:\d\d) \| [^|]+ \| (?P<dur>\d+h(?:\d+)?) \| "
    r"(?P<work>.*?)  \(api_id: (?P<id>[A-Z0-9]{15})\)(?P<rest>.*)$"
)


def parse_entries(text: str) -> list[Entry]:
    """Parses the bullet list returned by ListTimeEntries."""
    entries = []
    for line in text.splitlines():
        m = _ENTRY_RE.match(line.strip())
        if not m:
            continue
        work = m["work"]
        task = re.search(r"\(task api_id: ([A-Z0-9]{15})\)", work)
        desc = work.split(" — ", 1)[1].strip() if " — " in work else ""
        entries.append(
            Entry(
                id=m["id"],
                start=datetime.strptime(m["start"], "%Y-%m-%d %H:%M"),
                minutes=parse_duration(m["dur"]),
                task_id=task[1] if task else None,
                description=desc,
                locked="[locked" in m["rest"],
            )
        )
    return entries


def slots_for(day: date, hours: WorkHours) -> list[datetime]:
    """Start times of the hourly slots on a workday."""
    if day.weekday() not in hours.workdays:
        return []
    return [at_hour(day, h) for h in range(hours.start_hour, hours.end_hour)]


def is_covered(slot: datetime, entries: list[Entry]) -> bool:
    """A slot counts as done once any entry overlaps it."""
    end = slot + timedelta(hours=1)
    return any(e.start < end and e.end > slot for e in entries)


def pending_slots(now: datetime, entries: list[Entry], skipped: set[datetime], hours: WorkHours) -> list[datetime]:
    """Today's hours that have ended but are neither logged in Orbit nor skipped."""
    return [
        s
        for s in slots_for(now.date(), hours)
        if s + timedelta(hours=1) <= now and s not in skipped and not is_covered(s, entries)
    ]


def entry_ending_at(slot: datetime, entries: list[Entry]) -> Entry | None:
    """The entry that ends exactly where this slot starts, if any."""
    return next((e for e in entries if e.end == slot), None)


def recent_task_ids(entries: list[Entry]) -> list[str]:
    """Task ids, most recently logged first, without duplicates."""
    seen: dict[str, None] = {}
    for e in sorted(entries, key=lambda e: e.start, reverse=True):
        if e.task_id:
            seen.setdefault(e.task_id)
    return list(seen)


def load_last_reminder(path: Path = LAST_REMINDER_FILE) -> datetime | None:
    try:
        return datetime.fromisoformat(read_json(path, None))
    except (TypeError, ValueError):  # missing or corrupt: just remind
        return None


def save_last_reminder(when: datetime, path: Path = LAST_REMINDER_FILE) -> None:
    write_json(path, when.isoformat())


def load_skipped(path: Path = STATE_FILE) -> set[datetime]:
    try:
        return {datetime.fromisoformat(s) for s in read_json(path, [])}
    except (TypeError, ValueError):  # corrupt: forget the skips rather than crash
        return set()


def save_skipped(skipped: set[datetime], path: Path = STATE_FILE) -> None:
    # Only keep the last two weeks around.
    cutoff = datetime.now() - timedelta(days=14)
    write_json(path, sorted(s.isoformat() for s in skipped if s > cutoff))
