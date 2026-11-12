import sys


def _reminder_due() -> bool:
    """Cheap check for the hourly timer, before the heavy Tk/MCP imports."""
    from .core import SettingsError, WorkHours, load_last_reminder, load_work_hours, now

    try:
        hours = load_work_hours()
    except SettingsError:
        hours = WorkHours()  # the popup run reports the broken file, but only during (default) work hours
    return hours.should_remind(now(), load_last_reminder())


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "popup"
    if cmd == "setup":
        from .configure import setup

        setup()
        return
    if cmd == "scheduled" and not _reminder_due():
        return

    from . import orbit

    if cmd == "login":
        orbit.list_tools()
        print("Logged in to Teamleader Orbit.")
    elif cmd == "tools":
        import json

        for t in orbit.list_tools():
            print(json.dumps({"name": t.name, "description": t.description, "input": t.input_schema}))
    else:
        from .app import run

        run(scheduled=cmd == "scheduled")
