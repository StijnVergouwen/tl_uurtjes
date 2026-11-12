"""`tl-uurtjes setup`: asks for your working hours once and saves them."""

from .core import SETTINGS_FILE, WorkHours, load_work_hours, parse_workdays, save_work_hours


def _ask(prompt: str, default: str, parse):
    while True:
        try:
            return parse(input(f"{prompt} [{default}]: ").strip() or default)
        except ValueError as e:
            print(f"  {e}")


def setup() -> None:
    current = load_work_hours()
    while True:
        try:
            # WorkHours itself validates the combination; on an error all three are asked again.
            hours = WorkHours(
                _ask("Start of your working day (hour)", str(current.start_hour), int),
                _ask("End of your working day (hour, max 23)", str(current.end_hour), int),
                _ask(
                    "Workdays (1 = Monday ... 7 = Sunday, e.g. 1-5 or 1-3,5)",
                    ",".join(str(d + 1) for d in current.workdays),
                    parse_workdays,
                ),
            )
            break
        except ValueError as e:
            print(f"  {e}")
    save_work_hours(hours)
    print(f"Saved to {SETTINGS_FILE}; the popup follows these hours from now on.")
