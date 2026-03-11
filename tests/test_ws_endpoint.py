"""Integration tests for the /api/ws WebSocket endpoint.

Uses a lightweight test FastAPI app (no engine) to verify connection
acceptance, subscribe/unsubscribe, and event delivery via the
dual-task WebSocket handler.

Note: The Starlette WebSocket TestClient uses anyio which runs the
ASGI app in a separate thread.  To publish events that the writer
coroutine can pick up, we schedule the publish into the app's event
loop via a helper HTTP endpoint.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from lunar_sandbox.api.schemas import WsEnvelope
from lunar_sandbox.api.ws import ConnectionManager, EventHub
from lunar_sandbox.api.ws.endpoint import websocket_handler


def _make_test_app() -> FastAPI:
    """Create a minimal FastAPI app with WS endpoint + publish helper."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.ws_manager = ConnectionManager()
        app.state.event_hub = EventHub(app.state.ws_manager)
        yield

    test_app = FastAPI(lifespan=lifespan)

    @test_app.websocket("/api/ws")
    async def ws_route(websocket: WebSocket) -> None:
        await websocket_handler(websocket, test_app.state.ws_manager)

    @test_app.post("/test/publish")
    async def publish_helper(topic: str, payload: str) -> dict:
        """Helper endpoint to publish events from the correct event loop."""
        test_app.state.ws_manager.publish(topic, payload)
        return {"published": True}

    return test_app


@pytest.fixture()
def app_and_client():
    """Yield (app, client) with lifespan started."""
    test_app = _make_test_app()
    with TestClient(test_app) as client:
        yield test_app, client


class TestWsEndpoint:
    """Integration tests for the WebSocket endpoint via TestClient."""

    def test_ws_connect_and_subscribe(self, app_and_client) -> None:
        """Client can connect and send a subscribe message."""
        _app, client = app_and_client
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"subscribe": "sandbox:test"})
            # Connection accepted and subscribe processed without error

    def test_ws_receive_published_event(self, app_and_client) -> None:
        """Client receives an event published to a matching topic."""
        test_app, client = app_and_client

        # We need two concurrent activities: a WS client waiting for
        # messages, and an HTTP POST that triggers publish.  The
        # Starlette TestClient runs WS and HTTP in the same event loop
        # via anyio.  To avoid deadlock we use a background thread for
        # the HTTP POST while the main thread blocks on ws.receive_json.
        from threading import Thread

        envelope = WsEnvelope(
            type="trace_event",
            topic="sandbox:test:episode:1",
            timestamp=time.time(),
            payload={"step_idx": 0},
        )

        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"subscribe": "sandbox:test"})

            def do_publish() -> None:
                import time as _t

                _t.sleep(0.15)
                client.post(
                    "/test/publish",
                    params={
                        "topic": "sandbox:test:episode:1",
                        "payload": envelope.model_dump_json(),
                    },
                )

            t = Thread(target=do_publish)
            t.start()
            data = ws.receive_json()
            t.join()

            assert data["type"] == "trace_event"
            assert data["topic"] == "sandbox:test:episode:1"
            assert data["payload"]["step_idx"] == 0

    def test_ws_unsubscribe_stops_events(self, app_and_client) -> None:
        """After unsubscribe, client no longer receives events for that topic."""
        test_app, client = app_and_client
        from threading import Thread

        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"subscribe": "sandbox:unsub-test"})

            # First, verify events arrive while subscribed
            envelope_json = WsEnvelope(
                type="test",
                topic="sandbox:unsub-test",
                timestamp=time.time(),
                payload={"seq": 1},
            ).model_dump_json()

            def publish_first() -> None:
                import time as _t

                _t.sleep(0.15)
                client.post(
                    "/test/publish",
                    params={
                        "topic": "sandbox:unsub-test",
                        "payload": envelope_json,
                    },
                )

            t = Thread(target=publish_first)
            t.start()
            data = ws.receive_json()
            t.join()
            assert data["payload"]["seq"] == 1

            # Unsubscribe, then subscribe to a sentinel topic
            ws.send_json({"unsubscribe": "sandbox:unsub-test"})
            ws.send_json({"subscribe": "sentinel"})

            def publish_after_unsub() -> None:
                import time as _t

                _t.sleep(0.15)
                # This should NOT be delivered (unsubscribed)
                client.post(
                    "/test/publish",
                    params={
                        "topic": "sandbox:unsub-test",
                        "payload": WsEnvelope(
                            type="should_not_arrive",
                            topic="sandbox:unsub-test",
                            timestamp=time.time(),
                            payload={"seq": 2},
                        ).model_dump_json(),
                    },
                )
                _t.sleep(0.05)
                # This SHOULD be delivered (sentinel)
                client.post(
                    "/test/publish",
                    params={
                        "topic": "sentinel",
                        "payload": WsEnvelope(
                            type="sentinel",
                            topic="sentinel",
                            timestamp=time.time(),
                            payload={},
                        ).model_dump_json(),
                    },
                )

            t2 = Thread(target=publish_after_unsub)
            t2.start()
            data2 = ws.receive_json()
            t2.join()
            # The first message received should be the sentinel
            assert data2["type"] == "sentinel"
