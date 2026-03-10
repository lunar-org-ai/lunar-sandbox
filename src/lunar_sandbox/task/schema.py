"""Pydantic models for task definition and repo source configuration.

A task is the unit of evaluation: it specifies what code to work on,
what instructions the agent receives, and how to score the result.
Tasks are defined in YAML and validated here via Pydantic v2 models.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from lunar_sandbox.filesystem.fingerprint import compute_fingerprint

__all__ = [
    "RepoSource",
    "TaskDefinition",
]


class RepoSource(BaseModel):
    """Source repository for a task -- either a git URL or a local path.

    At least one of ``url`` or ``path`` must be provided.  Both may be
    set simultaneously (e.g., URL as primary with local fallback), but
    the typical case is exactly one.
    """

    url: str | None = None
    path: str | None = None
    ref: str | None = None
    depth: int = 1

    @model_validator(mode="after")
    def _require_url_or_path(self) -> RepoSource:
        if not self.url and not self.path:
            msg = "RepoSource requires at least one of 'url' or 'path'"
            raise ValueError(msg)
        return self


class TaskDefinition(BaseModel):
    """Full task definition parsed from YAML.

    Required fields: ``repo``, ``instructions``, ``test_command``.
    Everything else has sensible defaults.  The ``repo`` field accepts
    a string shorthand that is auto-converted to a :class:`RepoSource`.
    """

    name: str = ""
    repo: RepoSource | str
    instructions: str
    test_command: str
    setup_commands: list[str] = Field(default_factory=list)
    scoring_script: str | None = None
    scoring_parser: str | None = None
    timeout: int = 1800
    max_steps: int = 200
    runtime: str = "python3.12"
    deps: list[str] = Field(default_factory=list)
    extras: dict[str, str] = Field(default_factory=dict)
    fingerprint: str | None = None
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("repo", mode="before")
    @classmethod
    def _coerce_repo_string(cls, v: object) -> object:
        """Convert a plain string into a :class:`RepoSource`.

        Strings starting with ``http://``, ``https://``, or ``git@``
        are treated as git URLs; everything else is treated as a local
        filesystem path.
        """
        if isinstance(v, str):
            if v.startswith(("http://", "https://", "git@")):
                return RepoSource(url=v)
            return RepoSource(path=v)
        return v

    def derive_fingerprint(self) -> str:
        """Return the environment fingerprint for pool matching.

        If an explicit ``fingerprint`` override is set on the task, it
        is returned as-is.  Otherwise the fingerprint is computed from
        ``runtime``, ``deps``, and ``extras`` via
        :func:`~lunar_sandbox.filesystem.fingerprint.compute_fingerprint`.
        """
        if self.fingerprint is not None:
            return self.fingerprint
        return compute_fingerprint(
            self.runtime,
            self.deps,
            self.extras or None,
        )
