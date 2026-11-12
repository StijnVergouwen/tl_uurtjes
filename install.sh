#!/usr/bin/env bash
# Installs the hourly popup as a systemd user timer.
set -euo pipefail
cd "$(dirname "$0")"
uv sync
.venv/bin/tl-uurtjes setup   # asks your working hours
mkdir -p ~/.config/systemd/user
sed "s|@REPO@|$PWD|g" systemd/tl-uurtjes.service > ~/.config/systemd/user/tl-uurtjes.service
cp systemd/tl-uurtjes.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tl-uurtjes.timer
systemctl --user list-timers tl-uurtjes.timer
