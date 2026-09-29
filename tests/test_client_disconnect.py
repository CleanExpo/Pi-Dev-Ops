"""A caller that hangs up mid-upload must not crash the app.

Railway production logged `starlette.requests.ClientDisconnect` tracebacks from
`routes/webhooks.py` (`await request.body()`) whenever GitHub or Linear dropped
the connection before the body arrived. The app now answers a quiet 400.

The handler is exercised on a minimal app rather than by driving a request
through the full production app: a full-app request here perturbed the
sys.modules-reloading fixtures in tests/test_mesh_*.py later in the run.
"""

import asyncio
import logging

from fastapi import FastAPI, Request
from starlette.requests import ClientDisconnect

from app.server.app_factory import _client_disconnected, app


def test_handler_is_registered_on_the_real_app() -> None:
    assert app.exception_handlers.get(ClientDisconnect) is _client_disconnected


def _post_with_disconnect(target: FastAPI) -> list[dict]:
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "https", "path": "/hook", "raw_path": b"/hook",
        "query_string": b"", "root_path": "", "headers": [(b"host", b"testserver")],
        "client": ("203.0.113.9", 5555), "server": ("testserver", 443),
    }
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(target(scope, receive, send))
    return sent


def test_body_read_after_disconnect_is_a_400_not_a_crash(caplog) -> None:
    mini = FastAPI()
    mini.add_exception_handler(ClientDisconnect, _client_disconnected)

    @mini.post("/hook")
    async def hook(request: Request) -> dict:
        await request.body()  # the exact call that crashed in routes/webhooks.py
        return {"ok": True}

    with caplog.at_level(logging.WARNING):
        sent = _post_with_disconnect(mini)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 400
    assert "client disconnected" in caplog.text
