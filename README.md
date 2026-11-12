# tl-uurtjes

Every hour on workdays (10:00 … 18:00) a small window asks which Teamleader Orbit task you
worked on the previous hour, and walks you through every hour since 9:00 that isn't logged yet.

It talks to the official Orbit MCP server (`https://api.orbit.teamleader.eu/mcp`) with your own
OAuth login; tokens live in `~/.config/tl_uurtjes/oauth.json`.

## Setup

```bash
uv run tl-uurtjes login   # one-time browser login to Orbit
./install.sh              # installs + starts the systemd user timer
```

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
