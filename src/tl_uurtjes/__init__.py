import sys


def main() -> None:
    from . import orbit

    cmd = sys.argv[1] if len(sys.argv) > 1 else "popup"
    if cmd == "login":
        orbit.list_tools()
        print("Logged in to Teamleader Orbit.")
    elif cmd == "tools":
        import json

        for t in orbit.list_tools():
            print(json.dumps({"name": t.name, "description": t.description, "input": t.input_schema}))
    else:
        from .app import run

        run()
