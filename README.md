# tl-uurtjes

At the end of every work hour a small window asks which Teamleader Orbit task you worked on,
and walks you through every hour of today that isn't logged yet. Your working hours and
workdays are personal: you set them once (default Mon–Fri, 9:00–18:00).

It talks to the official Orbit MCP server (`https://api.orbit.teamleader.eu/mcp`) with your own
OAuth login; tokens live in `~/.config/tl_uurtjes/oauth.json`.

## Setup

```bash
./install.sh   # logs you in to Orbit (first time), asks your working hours, starts the hourly timer
```

Working hours are stored in `~/.config/tl_uurtjes/settings.json`. To change them later, run
`uv run tl-uurtjes setup` again (Enter keeps the current value); no reinstall needed.
Hours are whole hours, e.g. start `8` and end `17` gives the slots 8:00–9:00 … 16:00–17:00.
If your laptop was asleep when a work hour ended, you get one popup when it wakes up (also in
the evening). Only today's hours are asked; earlier days you fill in in Orbit itself.

The repo can live anywhere: `install.sh` writes the checkout's absolute path into the installed
service. If you move or re-clone the repo, run `./install.sh` again from the new location.

Logins are per machine: everyone logs in once for the app (`install.sh` does this, or run
`uv run tl-uurtjes login`), and `/mcp` → `teamleader-orbit` in Claude Code if they want Claude to
use Orbit too. If the popup ever says you're not logged in, run `uv run tl-uurtjes login`.

Popup never shows up? Check `journalctl --user -u tl-uurtjes` for errors.

## Using the popup

- Type to filter tasks, ↑/↓ to choose; ★ marks tasks you logged recently.
- **Enter** logs the hour; **Ctrl+Enter** logs every remaining open hour on that task.
- **Didn't work** marks the hour as skipped (stored locally, it won't ask again).
- **Esc / Later** closes the window; open hours come back at the next popup.
- An hour counts as done as soon as any Orbit entry overlaps it, so time logged elsewhere is respected.
- Logging the same task (and description) as the hour before extends that entry instead of adding a new one.

Run it by hand any time with `uv run tl-uurtjes`.

## Testing

```bash
uv run pytest
TL_UURTJES_DRY_RUN=1 TL_UURTJES_NOW="2026-11-12 14:05" uv run tl-uurtjes   # no writes, fake clock
```
