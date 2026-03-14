#!/bin/bash
set -e

# Start Xvfb virtual framebuffer
Xvfb "${DISPLAY}" -screen 0 "${RESOLUTION}x${COLOR_DEPTH}" -ac +extension GLX +render -noreset &
XVFB_PID=$!

echo "[xvfb] Starting Xvfb on ${DISPLAY} at ${RESOLUTION}x${COLOR_DEPTH}..."

# Poll xdpyinfo until Xvfb is ready (timeout 5s)
TIMEOUT=5
ELAPSED=0
INTERVAL=0.1

while ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; do
    if (( $(echo "$ELAPSED >= $TIMEOUT" | bc -l) )); then
        echo "[xvfb] ERROR: Xvfb did not become ready within ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep "${INTERVAL}"
    ELAPSED=$(echo "$ELAPSED + $INTERVAL" | bc)
done

echo "[xvfb] Xvfb ready on ${DISPLAY}"
