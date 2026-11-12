#!/usr/bin/env bash
# Installs the hourly popup as a systemd user timer. Safe to run again (e.g. after moving the repo).
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "uv is not installed: see https://docs.astral.sh/uv/" >&2; exit 1; }
[ -t 0 ] || { echo "Run ./install.sh from a terminal: it asks for your working hours." >&2; exit 1; }
case "$PWD" in
  *[[:space:]%\|\&]*) echo "The repo path '$PWD' contains a space or one of % | &, which systemd can't run from. Move the repo and try again." >&2; exit 1 ;;
esac

# --reinstall-package refreshes the absolute paths inside .venv when the repo was moved.
uv sync --reinstall-package tl-uurtjes
[ -f ~/.config/tl_uurtjes/oauth.json ] || .venv/bin/tl-uurtjes login
.venv/bin/tl-uurtjes setup

mkdir -p ~/.config/systemd/user
sed "s|@REPO@|$PWD|g" systemd/tl-uurtjes.service > ~/.config/systemd/user/tl-uurtjes.service
cp systemd/tl-uurtjes.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tl-uurtjes.timer
systemctl --user list-timers tl-uurtjes.timer

if ! systemctl --user show-environment | grep -qE '^(DISPLAY|WAYLAND_DISPLAY)='; then
  echo
  echo "Warning: systemd doesn't know your display yet, so the timer can't open the popup."
  echo "Add this to your window manager's autostart (e.g. i3 config: exec --no-startup-id ...):"
  echo "  dbus-update-activation-environment --systemd DISPLAY XAUTHORITY WAYLAND_DISPLAY"
fi
