#!/bin/bash
set -e

echo "[openbox] Starting Openbox window manager..."
openbox --config-file /etc/xdg/openbox/rc.xml &

# Brief pause to let Openbox initialize its event loop
sleep 0.5

echo "[openbox] Openbox started"
