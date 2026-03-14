"""CUA-specific exception types.

All exceptions inherit from :class:`~lunar_sandbox.sandbox.errors.SandboxError`
so callers can catch either the specific subclass or the broad base class.

Usage::

    from lunar_sandbox.sandbox.cua_errors import ActionTimeout, ActionFailed, ContainerError

Hierarchy::

    SandboxError
    ├── ActionTimeout   -- xdotool / maim command exceeded timeout
    ├── ActionFailed    -- xdotool / maim returned non-zero exit code
    └── ContainerError  -- container unhealthy or unreachable
"""

from __future__ import annotations

from lunar_sandbox.sandbox.errors import SandboxError


class ActionTimeout(SandboxError):
    """Raised when an xdotool or maim command exceeds its allowed timeout.

    Attributes:
        action_type: Name of the action that timed out (e.g. ``"screenshot"``).
        timeout_seconds: The timeout limit that was exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        action_type: str = "",
        timeout_seconds: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.action_type = action_type
        self.timeout_seconds = timeout_seconds


class ActionFailed(SandboxError):
    """Raised when an action command returns a non-zero exit code.

    Attributes:
        action_type: Name of the action that failed (e.g. ``"left_click"``).
        exit_code: Exit code returned by the command.
        stderr: Captured standard error output from the command.
    """

    def __init__(
        self,
        message: str,
        *,
        action_type: str = "",
        exit_code: int = -1,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.action_type = action_type
        self.exit_code = exit_code
        self.stderr = stderr


class ContainerError(SandboxError):
    """Raised when the CUA container is unhealthy or unreachable.

    Attributes:
        container_id: Docker container ID, or ``None`` if unknown.
    """

    def __init__(
        self,
        message: str,
        *,
        container_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.container_id = container_id
