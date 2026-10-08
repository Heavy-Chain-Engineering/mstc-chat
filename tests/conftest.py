import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette
from starlette.types import Message as AsgiMessage

from backend.app import create_app
from backend.room import Room

CLASS_PASSWORD = "correct horse battery staple"
SESSION_SECRET = "test-session-secret-0123456789abcdef"
COOKIE_NAME = "__Host-session"
INDEX_HTML = "<!doctype html><title>MSTC Chat</title>"
TAB_A = "00000000-0000-4000-8000-00000000000a"
TAB_B = "00000000-0000-4000-8000-00000000000b"

type AppFactory = Callable[..., Starlette]
type ClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(INDEX_HTML)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('app');")
    return tmp_path


@pytest.fixture
def make_app(static_dir: Path) -> AppFactory:
    """Builds the real app with test secrets, a fast wrong-password wait and short streams."""

    def build(**overrides: object) -> Starlette:
        settings: dict[str, object] = {
            "class_password": CLASS_PASSWORD,
            "session_secret": SESSION_SECRET,
            "static_dir": static_dir,
            "wrong_password_delay": 0.01,
            "stream_lifetime": 2.0,
            "presence_grace": 0.0,
        }
        return create_app(**(settings | overrides))

    return build


@pytest.fixture
def app(make_app: AppFactory) -> Starlette:
    return make_app()


@pytest.fixture
async def make_client(app: Starlette) -> AsyncIterator[ClientFactory]:
    """Opens one httpx client per participant, each with its own cookie jar."""
    async with AsyncExitStack() as stack:

        async def open_client() -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://testserver"
            )
            return await stack.enter_async_context(client)

        yield open_client


@pytest.fixture
async def client(make_client: ClientFactory) -> httpx.AsyncClient:
    return await make_client()


def room_of(app: Starlette) -> Room:
    room = app.state.room
    assert isinstance(room, Room)
    return room


async def sign_in(client: httpx.AsyncClient, name: str = "Avery") -> str:
    """Signs the client in and returns its session cookie value."""
    response = await client.post("/api/login", json={"name": name, "password": CLASS_PASSWORD})
    response.raise_for_status()
    return client.cookies[COOKIE_NAME]


class OpenStream:
    """Drives GET /api/stream over raw ASGI, so a test reads each event as the server writes it.

    httpx's ASGITransport returns a body only after the response ends, which cannot show
    delivery while a stream is open or a client that disconnects mid-stream.
    """

    def __init__(self, app: Starlette, path: str, headers: dict[str, str]) -> None:
        self.status: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        self._chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._buffer = ""
        self._request_sent = False
        self._disconnect = asyncio.Event()
        path_part, _, query = path.partition("?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path_part,
            "raw_path": path_part.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")]
            + [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 443),
        }
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> AsgiMessage:
        if not self._request_sent:
            self._request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: AsgiMessage) -> None:
        if message["type"] == "http.response.start":
            self.status.set_result(message["status"])
        elif message["type"] == "http.response.body":
            await self._chunks.put(message.get("body", b""))
            if not message.get("more_body", False):
                await self._chunks.put(None)

    async def next_event(self, timeout: float = 2.0) -> dict[str, str] | None:
        """Returns the next event's fields, or None when the stream has ended."""
        async with asyncio.timeout(timeout):
            while "\n\n" not in self._buffer:
                chunk = await self._chunks.get()
                if chunk is None:
                    return None
                self._buffer += chunk.decode()
        block, _, self._buffer = self._buffer.partition("\n\n")
        return dict(line.split(": ", 1) for line in block.split("\n"))

    async def events_until_end(self, timeout: float = 2.0) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        async with asyncio.timeout(timeout):
            while (event := await self.next_event(timeout)) is not None:
                events.append(event)
        return events

    async def events_until(self, kind: str, timeout: float = 2.0) -> list[dict[str, str]]:
        """Returns the events up to and including the first one of this kind."""
        events: list[dict[str, str]] = []
        async with asyncio.timeout(timeout):
            while (event := await self.next_event(timeout)) is not None:
                events.append(event)
                if event.get("event") == kind:
                    return events
        raise EOFError(f"the stream ended before a {kind} event")

    async def close(self) -> None:
        self._disconnect.set()
        await asyncio.wait_for(self.task, timeout=2.0)


async def open_stream(
    app: Starlette, cookie: str | None, tab: str = TAB_A, last_event_id: str | None = None
) -> OpenStream:
    headers = {} if cookie is None else {"cookie": f"{COOKIE_NAME}={cookie}"}
    if last_event_id is not None:
        headers["last-event-id"] = last_event_id
    stream = OpenStream(app, f"/api/stream?tab={tab}", headers)
    await asyncio.wait_for(asyncio.shield(stream.status), timeout=2.0)
    return stream


def data_of(event: dict[str, str]) -> dict[str, object]:
    parsed = json.loads(event["data"])
    assert isinstance(parsed, dict)
    return parsed
