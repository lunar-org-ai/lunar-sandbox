"""YAML task file loading and validation.

Provides three entry points for creating a :class:`TaskDefinition`:

- :func:`load_task` -- from a YAML file path
- :func:`load_task_from_string` -- from a YAML string
- :func:`load_task_from_dict` -- from a pre-parsed dictionary
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lunar_sandbox.task.schema import TaskDefinition

__all__ = [
    "load_task",
    "load_task_from_dict",
    "load_task_from_string",
]


def load_task(yaml_path: Path) -> TaskDefinition:
    """Load a task definition from a YAML file.

    Args:
        yaml_path: Path to the YAML task file.

    Returns:
        Validated :class:`TaskDefinition`.

    Raises:
        FileNotFoundError: If *yaml_path* does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
        pydantic.ValidationError: If the parsed data fails schema validation.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        msg = f"Task file not found: {yaml_path}"
        raise FileNotFoundError(msg)

    raw = yaml_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    return TaskDefinition.model_validate(data)


def load_task_from_string(yaml_string: str) -> TaskDefinition:
    """Load a task definition from a YAML string.

    Args:
        yaml_string: YAML-formatted string.

    Returns:
        Validated :class:`TaskDefinition`.

    Raises:
        yaml.YAMLError: If the string contains invalid YAML.
        pydantic.ValidationError: If the parsed data fails schema validation.
    """
    data = yaml.safe_load(yaml_string)
    return TaskDefinition.model_validate(data)


def load_task_from_dict(data: dict) -> TaskDefinition:
    """Load a task definition from a dictionary.

    Args:
        data: Dictionary matching the :class:`TaskDefinition` schema.

    Returns:
        Validated :class:`TaskDefinition`.

    Raises:
        pydantic.ValidationError: If *data* fails schema validation.
    """
    return TaskDefinition.model_validate(data)
