"""Unit tests for action executor + client IPC round-trip.

Tests the full ActionExecutor server and ActionClient communication
over real Unix domain sockets. Each test starts an executor, connects
a client, sends actions, verifies responses, and cleans up.

Note: Unix domain socket paths have a ~104 char limit on macOS, so
socket files are placed under /tmp with short names instead of using
pytest's tmp_path (which generates long paths).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from lunar_sandbox.actions.client import ActionClient
from lunar_sandbox.actions.executor import ActionExecutor
from lunar_sandbox.actions.types import ActionStatus


def _run(coro):
    """Helper to run async tests."""
    return asyncio.run(coro)


@pytest.fixture
def sock_path():
    """Provide a short socket path that fits Unix domain socket limits."""
    # Use tempfile to create a short unique path under /tmp.
    fd, path = tempfile.mkstemp(suffix=".sock", prefix="ls_", dir="/tmp")
    os.close(fd)
    os.unlink(path)  # We just need the path, not the file.
    yield path
    # Cleanup in case test didn't remove it.
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


class TestExecutorLifecycle:
    """Tests for executor start/stop lifecycle."""

    def test_executor_start_stop(self, tmp_path: Path, sock_path: str) -> None:
        """Starts and stops cleanly, socket file created/removed."""

        async def _test():
            executor = ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            )
            await executor.start()
            assert os.path.exists(sock_path)

            await executor.stop()
            assert not os.path.exists(sock_path)

        _run(_test())

    def test_executor_context_manager(self, tmp_path: Path, sock_path: str) -> None:
        """Executor works as async context manager."""

        async def _test():
            async with ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            ) as executor:
                assert os.path.exists(sock_path)
                assert executor is not None

            assert not os.path.exists(sock_path)

        _run(_test())


class TestIPCRoundtrip:
    """Tests for full executor + client IPC round-trips."""

    def test_roundtrip_execute_command(self, tmp_path: Path, sock_path: str) -> None:
        """Full IPC round-trip for execute_command."""

        async def _test():
            async with ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            ):
                client = ActionClient(socket_path=sock_path)
                await client.connect(timeout=5.0)

                try:
                    resp = await client.execute_command("echo ipc_works")
                    assert resp.status == ActionStatus.SUCCESS
                    assert "ipc_works" in resp.stdout
                    assert resp.exit_code == 0
                finally:
                    await client.disconnect()

        _run(_test())

    def test_roundtrip_read_file(self, tmp_path: Path, sock_path: str) -> None:
        """Full IPC round-trip for read_file."""
        test_file = tmp_path / "hello.txt"
        test_file.write_text("hello from file")

        async def _test():
            async with ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            ):
                client = ActionClient(socket_path=sock_path)
                await client.connect(timeout=5.0)

                try:
                    resp = await client.read_file("hello.txt")
                    assert resp.status == ActionStatus.SUCCESS
                    assert resp.output == "hello from file"
                finally:
                    await client.disconnect()

        _run(_test())

    def test_roundtrip_write_file(self, tmp_path: Path, sock_path: str) -> None:
        """Full IPC round-trip for write_file."""

        async def _test():
            async with ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            ):
                client = ActionClient(socket_path=sock_path)
                await client.connect(timeout=5.0)

                try:
                    resp = await client.write_file("new_file.txt", "content here")
                    assert resp.status == ActionStatus.SUCCESS
                    assert (tmp_path / "new_file.txt").read_text() == "content here"
                finally:
                    await client.disconnect()

        _run(_test())

    def test_roundtrip_submit(self, tmp_path: Path, sock_path: str) -> None:
        """Full IPC round-trip for submit."""

        async def _test():
            async with ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            ):
                client = ActionClient(socket_path=sock_path)
                await client.connect(timeout=5.0)

                try:
                    resp = await client.submit("all done")
                    assert resp.status == ActionStatus.SUCCESS
                    assert resp.output["submitted"] is True
                finally:
                    await client.disconnect()

        _run(_test())

    def test_multiple_actions(self, tmp_path: Path, sock_path: str) -> None:
        """Multiple sequential actions on same connection."""

        async def _test():
            async with ActionExecutor(
                socket_path=sock_path,
                working_dir=tmp_path,
            ):
                client = ActionClient(socket_path=sock_path)
                await client.connect(timeout=5.0)

                try:
                    # Action 1: write a file.
                    resp1 = await client.write_file("multi.txt", "step 1")
                    assert resp1.status == ActionStatus.SUCCESS

                    # Action 2: read the file back.
                    resp2 = await client.read_file("multi.txt")
                    assert resp2.status == ActionStatus.SUCCESS
                    assert resp2.output == "step 1"

                    # Action 3: execute a command.
                    resp3 = await client.execute_command("echo step3")
                    assert resp3.status == ActionStatus.SUCCESS
                    assert "step3" in resp3.stdout

                    # Action 4: submit.
                    resp4 = await client.submit("done")
                    assert resp4.status == ActionStatus.SUCCESS
                finally:
                    await client.disconnect()

        _run(_test())


class TestClientEdgeCases:
    """Tests for client edge cases."""

    def test_client_connect_timeout(self) -> None:
        """Connection to non-existent socket times out."""
        client = ActionClient(socket_path="/tmp/ls_nonexistent.sock")

        async def _test():
            with pytest.raises(ConnectionError, match="Could not connect"):
                await client.connect(timeout=0.5, retry_interval=0.1)

        _run(_test())

    def test_client_send_without_connect(self) -> None:
        """Sending without connecting raises ConnectionError."""
        client = ActionClient(socket_path="/tmp/ls_nosuch.sock")

        async def _test():
            with pytest.raises(ConnectionError, match="Not connected"):
                await client.send_action("execute_command", {"command": "ls"})

        _run(_test())
