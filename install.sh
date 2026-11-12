#!/usr/bin/env bash
# Installs the hourly popup as a systemd user timer.
set -euo pipefail
cd "$(dirname "$0")"
uv sync
mkdir -p ~/.config/systemd/user
cp systemd/tl-uurtjes.service systemd/tl-uurtjes.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tl-uurtjes.timer
systemctl --user list-timers tl-uurtjes.timer
