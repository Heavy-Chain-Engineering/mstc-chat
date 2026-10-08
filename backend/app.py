"""The chat room over HTTP (ADR-01): routes, the event stream and the request guards.

This is the only module that imports Starlette (ADR-02). It turns requests into calls on the
room, session and Markdown modules, and their results into status codes and event-stream text.
It logs nothing, so no name, message, password, secret or cookie reaches a log (INV-002).
"""

import asyncio
import hashlib
import hmac
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from starlette.applications import Starlette
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.types import Message as AsgiMessage

from backend import session
from backend.room import (
    MAX_STREAMS,
    MAX_STREAMS_PER_NAME,
    PRESENCE_GRACE_SECONDS,
    Connection,
    Message,
    RejectedInput,
    Room,
    RoomEvent,
    check_text,
    clean_name,
)
from backend.safe_markdown import to_safe_html

COOKIE_NAME: Final = "__Host-session"
BODY_LIMIT_BYTES: Final = 32_768
RECONNECT_DELAY_MS: Final = 1000
STREAM_LIFETIME_SECONDS: Final = 20.0
WRONG_PASSWORD_DELAY_SECONDS: Final = 1.0
MAX_WAITING_LOGINS: Final = 20
STATIC_FOLDERS: Final = ("assets", "fonts", "brand")
TAB_ID: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SECURITY_HEADERS: Final = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

type ApiErrorCode = Literal[
    "bad_request",
    "signed_out",
    "wrong_password",
    "cross_site",
    "busy",
    "empty_message",
    "too_large",
]


class ApiError(Exception):
    def __init__(self, status: int, code: ApiErrorCode) -> None:
        super().__init__(code)
        self.status = status
        self.code: ApiErrorCode = code


class SecurityHeaders:
    """Adds the Content Security Policy and the other security headers to every response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: AsgiMessage) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(SECURITY_HEADERS)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimit:
    """Answers 413 to a body over the limit, by its Content-Length or by the bytes that arrive.

    Starlette's own max_body_size answers in plain text; this keeps the JSON error body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        length = Headers(scope=scope).get("content-length", "0")
        if not length.isdigit() or int(length) > BODY_LIMIT_BYTES:
            await _error_response(ApiError(413, "too_large"))(scope, receive, send)
            return
        received = 0

        async def receive_within_limit() -> AsgiMessage:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > BODY_LIMIT_BYTES:
                raise ApiError(413, "too_large")
            return message

        await self.app(scope, receive_within_limit, send)


class EventStream(StreamingResponse):
    """An event stream that removes its connection from the room however the stream ends."""

    def __init__(self, room: Room, connection: Connection, events: AsyncIterator[str]) -> None:
        super().__init__(events, media_type="text/event-stream")
        self.headers["Cache-Control"] = "no-cache"
        self._room = room
        self._connection = connection

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._room.disconnect(self._connection)


@dataclass
class ChatApi:
    room: Room
    password_digest: bytes
    session_secret: str
    stream_lifetime: float
    wrong_password_delay: float
    max_waiting_logins: int
    waiting_logins: int = 0

    async def login(self, request: Request) -> Response:
        body = await request.body()
        _refuse_cross_site(request)
        fields = _json_fields(body, ("name", "password"))
        name = clean_name(fields["name"])
        if self.waiting_logins >= self.max_waiting_logins:
            raise ApiError(429, "busy")
        if not hmac.compare_digest(_digest(fields["password"]), self.password_digest):
            await self._wait_after_wrong_password()
            raise ApiError(401, "wrong_password")
        token = session.issue(session.new_session(name), self.session_secret)
        response = JSONResponse({"name": name})
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=session.SESSION_MAX_AGE_SECONDS,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return response

    async def current_session(self, request: Request) -> Response:
        return JSONResponse({"name": self._session(request).name})

    async def post_message(self, request: Request) -> Response:
        body = await request.body()
        _refuse_cross_site(request)
        author = self._session(request)
        text = check_text(_json_fields(body, ("text",))["text"])
        html = to_safe_html(text)
        if not html.strip():
            raise ApiError(422, "empty_message")
        self.room.post(author.name, author.sid, html)
        return Response(status_code=204)

    async def stream(self, request: Request) -> Response:
        viewer = self._session(request)
        tab = request.query_params.get("tab", "")
        if TAB_ID.fullmatch(tab) is None:
            raise ApiError(400, "bad_request")
        last_event_id = request.headers.get("last-event-id")
        connection = self.room.connect(tab, viewer.name, viewer.sid, last_event_id)
        return EventStream(self.room, connection, self._events(connection))

    async def leave(self, request: Request) -> Response:
        body = await request.body()
        _refuse_cross_site(request)
        self._session(request)
        tab = _utf8(body)
        if TAB_ID.fullmatch(tab) is None:
            raise ApiError(400, "bad_request")
        self.room.leave(tab)
        return Response(status_code=204)

    def _session(self, request: Request) -> session.Session:
        found = session.read(request.cookies.get(COOKIE_NAME), self.session_secret)
        if found is None:
            raise ApiError(401, "signed_out")
        return found

    async def _wait_after_wrong_password(self) -> None:
        self.waiting_logins += 1
        try:
            await asyncio.sleep(self.wrong_password_delay)
        finally:
            self.waiting_logins -= 1

    async def _events(self, connection: Connection) -> AsyncIterator[str]:
        """Writes retry, hello, the replay and presence, then live events until the lifetime."""
        yield f"retry: {RECONNECT_DELAY_MS}\n\n"
        yield _event("hello", {"instance": self.room.instance})
        for message in connection.replay:
            yield self._message_event(message, connection)
        yield _event("presence", {"names": self.room.names()})
        deadline = asyncio.get_running_loop().time() + self.stream_lifetime
        while not connection.is_overflowed:
            try:
                async with asyncio.timeout_at(deadline):
                    room_event = await connection.queue.get()
            except TimeoutError:
                return
            yield self._render(room_event, connection)

    def _render(self, room_event: RoomEvent, connection: Connection) -> str:
        if isinstance(room_event, Message):
            return self._message_event(room_event, connection)
        return _event("presence", {"names": list(room_event.names)})

    def _message_event(self, message: Message, connection: Connection) -> str:
        received_at = message.received_at.isoformat(timespec="milliseconds")
        payload = {
            "seq": message.seq,
            "author": message.author,
            "html": message.html,
            "receivedAt": received_at.replace("+00:00", "Z"),
            "own": message.author_sid == connection.sid,
        }
        return _event("message", payload, f"{self.room.instance}:{message.seq}")


def _event(name: str, payload: object, event_id: str | None = None) -> str:
    """One event; json.dumps escapes newlines and non-ASCII, so data stays one line."""
    id_line = "" if event_id is None else f"id: {event_id}\n"
    return f"event: {name}\n{id_line}data: {json.dumps(payload)}\n\n"


def _refuse_cross_site(request: Request) -> None:
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise ApiError(403, "cross_site")


def _utf8(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ApiError(400, "bad_request") from error


def _json_fields(body: bytes, names: tuple[str, ...]) -> dict[str, str]:
    """Returns the named string fields of a JSON object body, or raises bad_request."""
    try:
        parsed: object = json.loads(_utf8(body))
    except (ValueError, RecursionError) as error:
        raise ApiError(400, "bad_request") from error
    if not isinstance(parsed, dict):
        raise ApiError(400, "bad_request")
    fields = {name: parsed.get(name) for name in names}
    strings = {name: value for name, value in fields.items() if isinstance(value, str)}
    if len(strings) != len(names) or not all(_is_valid_unicode(v) for v in strings.values()):
        raise ApiError(400, "bad_request")
    return strings


def _is_valid_unicode(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _digest(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def _error_response(error: ApiError | RejectedInput) -> Response:
    if isinstance(error, ApiError):
        return JSONResponse({"error": error.code}, status_code=error.status)
    status = 429 if error.code == "too_many_streams" else 422
    return JSONResponse({"error": error.code}, status_code=status)


def _handle_error(request: Request, error: Exception) -> Response:
    if not isinstance(error, ApiError | RejectedInput):
        raise error
    return _error_response(error)


def _routes(api: ChatApi, static_dir: Path) -> list[BaseRoute]:
    async def index(request: Request) -> Response:
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})

    routes: list[BaseRoute] = [
        Route("/", index),
        Route("/api/login", api.login, methods=["POST"]),
        Route("/api/session", api.current_session),
        Route("/api/messages", api.post_message, methods=["POST"]),
        Route("/api/stream", api.stream),
        Route("/api/leave", api.leave, methods=["POST"]),
    ]
    for folder in STATIC_FOLDERS:
        if (static_dir / folder).is_dir():
            routes.append(Mount(f"/{folder}", StaticFiles(directory=static_dir / folder)))
    return routes


def create_app(
    *,
    class_password: str,
    session_secret: str,
    static_dir: Path,
    stream_lifetime: float = STREAM_LIFETIME_SECONDS,
    presence_grace: float = PRESENCE_GRACE_SECONDS,
    wrong_password_delay: float = WRONG_PASSWORD_DELAY_SECONDS,
    max_waiting_logins: int = MAX_WAITING_LOGINS,
    max_streams: int = MAX_STREAMS,
    max_streams_per_name: int = MAX_STREAMS_PER_NAME,
) -> Starlette:
    room = Room(
        presence_grace=presence_grace,
        max_streams=max_streams,
        max_streams_per_name=max_streams_per_name,
    )
    api = ChatApi(
        room=room,
        password_digest=_digest(class_password),
        session_secret=session_secret,
        stream_lifetime=stream_lifetime,
        wrong_password_delay=wrong_password_delay,
        max_waiting_logins=max_waiting_logins,
    )
    app = Starlette(
        routes=_routes(api, static_dir),
        middleware=[Middleware(SecurityHeaders), Middleware(BodyLimit)],
        exception_handlers={ApiError: _handle_error, RejectedInput: _handle_error},
    )
    app.state.room = room
    return app
