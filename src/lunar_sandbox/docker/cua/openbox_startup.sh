#!/bin/bash
set -e

echo "[openbox] Starting Openbox window manager..."
openbox --config-file /etc/xdg/openbox/rc.xml &

# Brief pause to let Openbox initialize its event loop
sleep 0.5

# Set a Windows-style desktop background (classic teal)
xsetroot -solid '#008080' -display "${DISPLAY}" 2>/dev/null || true

# Launch desktop icons (file manager in desktop mode)
pcmanfm --desktop --display="${DISPLAY}" &

# Launch taskbar (tint2 gives a Windows-like bottom panel)
tint2 -display "${DISPLAY}" &

echo "[openbox] Openbox started"
