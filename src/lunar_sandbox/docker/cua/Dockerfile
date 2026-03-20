FROM ubuntu:22.04

# ── Build-time env ────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1

# ── Install all packages in a single layer to minimize image size ─────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # X11 virtual display and utilities
    xvfb \
    x11-utils \
    # Window manager (lightweight, no compositor overhead)
    openbox \
    # VNC server
    x11vnc \
    # Input injection
    xdotool \
    # Screenshot capture (stdout mode + JPEG quality flag)
    maim \
    # Browser (primary for CUA tasks)
    chromium-browser \
    # Desktop applications
    lxterminal \
    mousepad \
    pcmanfm \
    galculator \
    # Taskbar panel (Windows-like bottom bar)
    tint2 \
    # Background setting utility
    x11-xserver-utils \
    # D-Bus (required by some GTK apps in containers)
    dbus-x11 \
    # Fonts
    fonts-dejavu \
    # WebSocket bridge dependencies
    python3 \
    python3-pip \
    # Utilities
    procps \
    curl \
    bc \
    # noVNC static assets (served by websockify)
    novnc \
    && pip3 install --no-cache-dir websockify \
    # Clean up apt cache in the same layer
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ── Chromium wrapper script ───────────────────────────────────────────────────
# Bakes in required flags for Docker (no-sandbox, disable-gpu, disable-dev-shm-usage)
RUN printf '#!/bin/bash\nexec chromium-browser --no-sandbox --disable-gpu --disable-dev-shm-usage "$@"\n' \
    > /usr/local/bin/chromium-browser-wrapper \
    && chmod +x /usr/local/bin/chromium-browser-wrapper

# ── Copy entrypoint and service startup scripts ───────────────────────────────
COPY entrypoint.sh          /usr/local/bin/entrypoint.sh
COPY xvfb_startup.sh        /usr/local/bin/xvfb_startup.sh
COPY openbox_startup.sh     /usr/local/bin/openbox_startup.sh
COPY x11vnc_startup.sh      /usr/local/bin/x11vnc_startup.sh
COPY websockify_startup.sh  /usr/local/bin/websockify_startup.sh

RUN chmod +x \
    /usr/local/bin/entrypoint.sh \
    /usr/local/bin/xvfb_startup.sh \
    /usr/local/bin/openbox_startup.sh \
    /usr/local/bin/x11vnc_startup.sh \
    /usr/local/bin/websockify_startup.sh

# ── Copy Openbox configuration ────────────────────────────────────────────────
COPY openbox-rc.xml /etc/xdg/openbox/rc.xml

# ── Entrypoint ────────────────────────────────────────────────────────────────
# The entrypoint starts Xvfb -> Openbox -> x11vnc -> websockify then keeps
# the container alive via `tail -f /dev/null`. No CMD needed.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
