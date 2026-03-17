#!/bin/bash
set -e

echo "[openbox] Starting Openbox window manager..."
openbox --config-file /etc/xdg/openbox/rc.xml &

# Brief pause to let Openbox initialize its event loop
sleep 0.5

# Set a desktop background (classic teal)
xsetroot -solid '#008080' -display "${DISPLAY}" 2>/dev/null || true

# Launch taskbar (tint2 reads DISPLAY from env, no -display flag)
tint2 &

echo "[openbox] Openbox started"
