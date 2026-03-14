#!/bin/bash
set -e

# ── Environment defaults ──────────────────────────────────────────────────────
export DISPLAY="${DISPLAY:-:1}"
export RESOLUTION="${RESOLUTION:-1280x800}"
export COLOR_DEPTH="${COLOR_DEPTH:-24}"
export VNC_PORT="${VNC_PORT:-5900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"

echo "[entrypoint] CUA container starting..."
echo "[entrypoint] DISPLAY=${DISPLAY} RESOLUTION=${RESOLUTION} COLOR_DEPTH=${COLOR_DEPTH}"
echo "[entrypoint] VNC_PORT=${VNC_PORT} NOVNC_PORT=${NOVNC_PORT}"

# ── Service startup (ordered, each waits for its dependency) ─────────────────

# 1. Start Xvfb and wait until display is ready
source /usr/local/bin/xvfb_startup.sh

# 2. Start Openbox window manager (requires Xvfb ready)
source /usr/local/bin/openbox_startup.sh

# 3. Start x11vnc VNC server (requires Xvfb ready)
source /usr/local/bin/x11vnc_startup.sh

# 4. Start websockify WebSocket bridge (requires x11vnc running)
source /usr/local/bin/websockify_startup.sh

echo "[entrypoint] CUA desktop ready"

# ── Keep container alive ──────────────────────────────────────────────────────
exec tail -f /dev/null
