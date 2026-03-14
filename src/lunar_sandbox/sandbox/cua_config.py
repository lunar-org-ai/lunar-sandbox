"""CUA sandbox configuration.

Extends DockerSandboxConfig with display, VNC, and action timing fields
needed to run a CUA (Computer-Using Agent) container with X11 + xdotool
+ noVNC.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lunar_sandbox.sandbox.docker_config import DockerResourceLimits, DockerSandboxConfig

# Resource limits that suit a full GUI stack:
# browser + window manager + VNC server + websockify.
_CUA_RESOURCE_LIMITS = DockerResourceLimits(
    cpus=2.0,
    memory_bytes=2 * 1024 * 1024 * 1024,
    pids_limit=512,
)


@dataclass
class CUASandboxConfig(DockerSandboxConfig):
    """Per-sandbox configuration for CUA Docker containers.

    Extends :class:`DockerSandboxConfig` with fields specific to
    headless X11 display, VNC access, and xdotool action timing.

    The ``__post_init__`` hook injects display/VNC environment variables
    into ``extra_env`` automatically.  Any user-supplied ``extra_env``
    values take precedence (user values are merged last).

    Attributes:
        display_num: X11 display number used inside the container (```:N```).
        width: Horizontal display resolution in pixels.
        height: Vertical display resolution in pixels.
        color_depth: X11 color depth in bits (default 24-bit true colour).
        vnc_port: Port on which the VNC server listens inside the container.
        novnc_port: Port on which websockify (noVNC bridge) listens inside
            the container.
        action_delay_ms: Milliseconds to wait after each xdotool action.
            50 ms avoids X11 race conditions without noticeably slowing agents.
        screenshot_quality: JPEG quality passed to ``maim`` (1-10).
            7 produces ~80-150 KB images, balancing fidelity and payload size.
        screenshot_format: Image format string passed to ``maim`` (``jpg``).
        image: Docker image tag (overrides the base class default).
        resource_limits: Override default CUA resource limits if needed.
    """

    # X11 display settings
    display_num: int = 1
    width: int = 1280
    height: int = 800
    color_depth: int = 24

    # Network ports inside the container
    vnc_port: int = 5900
    novnc_port: int = 6080

    # Action timing and screenshot quality
    action_delay_ms: int = 50
    screenshot_quality: int = 7
    screenshot_format: str = "jpg"

    # Override base image default
    image: str = "lunar-cua:latest"

    # Override base resource limits default
    resource_limits: DockerResourceLimits = field(
        default_factory=lambda: DockerResourceLimits(
            cpus=2.0,
            memory_bytes=2 * 1024 * 1024 * 1024,
            pids_limit=512,
        )
    )

    def __post_init__(self) -> None:
        """Inject CUA-specific environment variables into extra_env.

        The container entrypoint reads these to configure Xvfb and VNC.
        Any user-supplied values in ``extra_env`` override the defaults.
        """
        cua_env: dict[str, str] = {
            "DISPLAY": self.display,
            "RESOLUTION": self.resolution,
            "COLOR_DEPTH": str(self.color_depth),
            "VNC_PORT": str(self.vnc_port),
            "NOVNC_PORT": str(self.novnc_port),
        }
        # User-supplied values win; merge cua_env first then overlay user values.
        merged = {**cua_env, **self.extra_env}
        self.extra_env = merged

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def resolution(self) -> str:
        """Display resolution string, e.g. ``"1280x800"``."""
        return f"{self.width}x{self.height}"

    @property
    def display(self) -> str:
        """X11 display identifier, e.g. ``":1"``."""
        return f":{self.display_num}"
