"""`tl-uurtjes setup`: asks for your working hours once and saves them."""

import sys

from .core import SETTINGS_FILE, SettingsError, WorkHours, load_work_hours, parse_hour, parse_workdays, save_work_hours


def _ask(prompt: str, default, parse):
    """Asks until the answer parses; Enter keeps the default."""
    while True:
        try:
            return parse(input(f"{prompt} [{default}]: ").strip() or str(default))
        except ValueError as e:
            print(f"  {e}")


def _hour_between(lo: int, hi: int):
    def parse(text: str) -> int:
        hour = parse_hour(text)
        if not lo <= hour <= hi:
            raise ValueError(f"use an hour from {lo} to {hi}")
        return hour

    return parse


def setup() -> None:
    try:
        current = load_work_hours()
    except SettingsError as e:
        print(f"Your saved settings are invalid ({e.__cause__}); starting from the defaults.\n")
        current = WorkHours()

    print("When do you work? The popup asks about every whole hour in between.")
    try:
        start = _ask("Start of your working day (hour, e.g. 9)", current.start_hour, _hour_between(0, 22))
        end = _ask(
            "End of your working day (hour, e.g. 17)",
            current.end_hour if current.end_hour > start else start + 1,
            _hour_between(start + 1, 23),
        )
        workdays = _ask(
            "Workdays (1 = Monday ... 7 = Sunday, e.g. 1-5 or 1-3,5)",
            ",".join(str(d + 1) for d in current.workdays),
            parse_workdays,
        )
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled, nothing saved.")
        sys.exit(1)

    hours = WorkHours(start, end, workdays)
    save_work_hours(hours)
    print(f"Saved to {SETTINGS_FILE}. Change it any time with `uv run tl-uurtjes setup`.")
