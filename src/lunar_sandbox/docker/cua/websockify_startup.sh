#!/bin/bash
set -e

echo "[websockify] Starting websockify on port ${NOVNC_PORT} -> VNC ${VNC_PORT}..."
websockify --web /usr/share/novnc "${NOVNC_PORT}" "localhost:${VNC_PORT}" &

echo "[websockify] websockify bridging port ${NOVNC_PORT} -> VNC ${VNC_PORT}"
