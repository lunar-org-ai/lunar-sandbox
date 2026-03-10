"""Unit tests for task definition schema and YAML loader.

Tests TaskDefinition, RepoSource validation, string coercion,
fingerprint derivation, and YAML/dict loading entry points.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lunar_sandbox.filesystem.fingerprint import compute_fingerprint
from lunar_sandbox.task.loader import (
    load_task_from_dict,
    load_task_from_string,
)
from lunar_sandbox.task.schema import RepoSource, TaskDefinition


class TestRepoSource:
    """Tests for RepoSource model."""

    def test_repo_string_url(self) -> None:
        """String 'https://...' auto-converts to RepoSource(url=...)."""
        task = TaskDefinition(
            repo="https://github.com/user/repo.git",
            instructions="Fix the bug",
            test_command="pytest",
        )
        assert isinstance(task.repo, RepoSource)
        assert task.repo.url == "https://github.com/user/repo.git"
        assert task.repo.path is None

    def test_repo_string_local_path(self) -> None:
        """String '/tmp/...' auto-converts to RepoSource(path=...)."""
        task = TaskDefinition(
            repo="/tmp/my-repo",
            instructions="Fix the bug",
            test_command="pytest",
        )
        assert isinstance(task.repo, RepoSource)
        assert task.repo.path == "/tmp/my-repo"
        assert task.repo.url is None

    def test_repo_object(self) -> None:
        """Explicit RepoSource dict with url, ref, depth."""
        task = TaskDefinition(
            repo={"url": "https://github.com/user/repo.git", "ref": "main", "depth": 5},
            instructions="Fix the bug",
            test_command="pytest",
        )
        assert isinstance(task.repo, RepoSource)
        assert task.repo.url == "https://github.com/user/repo.git"
        assert task.repo.ref == "main"
        assert task.repo.depth == 5

    def test_repo_validation_neither(self) -> None:
        """RepoSource with neither url nor path raises ValidationError."""
        with pytest.raises(ValidationError, match="url.*path|path.*url|requires"):
            TaskDefinition(
                repo={"ref": "main"},
                instructions="Fix the bug",
                test_command="pytest",
            )


class TestTaskDefinition:
    """Tests for TaskDefinition model."""

    def test_minimal_task(self) -> None:
        """Only required fields: repo, instructions, test_command."""
        task = TaskDefinition(
            repo="https://github.com/user/repo.git",
            instructions="Fix the bug",
            test_command="pytest",
        )
        assert task.instructions == "Fix the bug"
        assert task.test_command == "pytest"

    def test_full_task(self) -> None:
        """All optional fields with non-default values."""
        task = TaskDefinition(
            name="my-task",
            repo="https://github.com/user/repo.git",
            instructions="Fix all bugs",
            test_command="pytest -v",
            setup_commands=["pip install -r requirements.txt"],
            scoring_script="python score.py",
            scoring_parser="pytest",
            timeout=600,
            max_steps=50,
            runtime="python3.11",
            deps=["numpy", "pandas"],
            extras={"cuda": "12.0"},
            fingerprint="abcd1234abcd1234",
            env={"DEBUG": "1"},
        )
        assert task.name == "my-task"
        assert task.setup_commands == ["pip install -r requirements.txt"]
        assert task.scoring_script == "python score.py"
        assert task.scoring_parser == "pytest"
        assert task.timeout == 600
        assert task.max_steps == 50
        assert task.runtime == "python3.11"
        assert task.deps == ["numpy", "pandas"]
        assert task.extras == {"cuda": "12.0"}
        assert task.fingerprint == "abcd1234abcd1234"
        assert task.env == {"DEBUG": "1"}

    def test_task_defaults(self) -> None:
        """Verify defaults: timeout=1800, max_steps=200, runtime='python3.12'."""
        task = TaskDefinition(
            repo="/tmp/repo",
            instructions="do stuff",
            test_command="pytest",
        )
        assert task.timeout == 1800
        assert task.max_steps == 200
        assert task.runtime == "python3.12"
        assert task.name == ""
        assert task.setup_commands == []
        assert task.scoring_script is None
        assert task.scoring_parser is None
        assert task.deps == []
        assert task.extras == {}
        assert task.fingerprint is None
        assert task.env == {}


class TestDeriveFingerprint:
    """Tests for TaskDefinition.derive_fingerprint()."""

    def test_derive_fingerprint_auto(self) -> None:
        """Returns 16-char hex from runtime+deps when no override."""
        task = TaskDefinition(
            repo="/tmp/repo",
            instructions="do stuff",
            test_command="pytest",
            runtime="python3.12",
            deps=["numpy", "pandas"],
        )
        fp = task.derive_fingerprint()
        assert len(fp) == 16
        int(fp, 16)  # Valid hex
        # Should match direct computation.
        expected = compute_fingerprint("python3.12", ["numpy", "pandas"])
        assert fp == expected

    def test_derive_fingerprint_override(self) -> None:
        """Returns explicit fingerprint when set."""
        task = TaskDefinition(
            repo="/tmp/repo",
            instructions="do stuff",
            test_command="pytest",
            fingerprint="custom_fp_value!",
        )
        assert task.derive_fingerprint() == "custom_fp_value!"


class TestLoadTask:
    """Tests for task loading functions."""

    def test_load_task_from_dict(self) -> None:
        """Basic dict loading."""
        data = {
            "repo": "https://github.com/user/repo.git",
            "instructions": "Fix the bug",
            "test_command": "pytest",
        }
        task = load_task_from_dict(data)
        assert task.instructions == "Fix the bug"
        assert isinstance(task.repo, RepoSource)
        assert task.repo.url == "https://github.com/user/repo.git"

    def test_load_task_from_string(self) -> None:
        """YAML string loading."""
        yaml_str = """\
repo: "https://github.com/user/repo.git"
instructions: "Fix the bug"
test_command: "pytest"
timeout: 900
"""
        task = load_task_from_string(yaml_str)
        assert task.instructions == "Fix the bug"
        assert task.timeout == 900

    def test_load_task_validation_error(self) -> None:
        """Missing required fields raises ValidationError."""
        with pytest.raises(ValidationError):
            load_task_from_dict({"name": "incomplete-task"})
