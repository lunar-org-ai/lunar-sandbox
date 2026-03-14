#!/bin/bash
set -e

echo "[x11vnc] Starting x11vnc on ${DISPLAY} port ${VNC_PORT}..."
x11vnc \
    -display "${DISPLAY}" \
    -forever \
    -shared \
    -rfbport "${VNC_PORT}" \
    -nopw \
    -xkb \
    -ncache 10 \
    -bg

# Verify the process started
sleep 0.3
if ! pgrep -x x11vnc >/dev/null 2>&1; then
    echo "[x11vnc] ERROR: x11vnc failed to start" >&2
    exit 1
fi

echo "[x11vnc] x11vnc listening on port ${VNC_PORT}"
