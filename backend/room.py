"""The chat room's rules: input limits, history, open streams and who is online (ADR-02).

All state lives on the one asyncio event loop (ADR-01), so no method here needs a lock.
"""

import asyncio
import re
import secrets
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

HISTORY_LIMIT = 200
NAME_MAX_LENGTH = 50
MESSAGE_MAX_LENGTH = 4000
EVENTS_WAITING_LIMIT = 200
MAX_STREAMS = 150
MAX_STREAMS_PER_NAME = 5
PRESENCE_GRACE_SECONDS = 5.0

# A forged header must not cost a huge integer parse, so the sequence part is capped at 15 digits.
LAST_EVENT_ID = re.compile(r"([0-9a-f]{16}):([0-9]{1,15})")

type RejectionCode = Literal[
    "bad_request",
    "name_blank",
    "name_too_long",
    "message_blank",
    "message_too_long",
    "too_many_streams",
]


class RejectedInput(Exception):
    """A rule refused an input; `code` is the stable error code the client maps to wording."""

    def __init__(self, code: RejectionCode) -> None:
        super().__init__(code)
        self.code: RejectionCode = code


@dataclass(frozen=True)
class Message:
    seq: int
    author: str
    author_sid: str
    html: str
    received_at: datetime


@dataclass(frozen=True)
class Presence:
    names: tuple[str, ...]


type RoomEvent = Message | Presence


@dataclass(eq=False)
class Connection:
    """One open event stream. `replay` holds the kept messages this stream has not seen."""

    tab: str
    name: str
    sid: str
    replay: list[Message]
    queue: asyncio.Queue[RoomEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=EVENTS_WAITING_LIMIT)
    )
    is_overflowed: bool = False


@dataclass(eq=False)
class _PresentTab:
    name: str
    connections: set[Connection] = field(default_factory=set)
    expiry: asyncio.TimerHandle | None = None


REFUSED_NAME_CATEGORIES = frozenset({"Cc", "Cf"})


def clean_name(raw: str) -> str:
    """Return the display name without surrounding whitespace, or raise RejectedInput.

    A control or format character, such as a newline or a right-to-left override, is refused
    before trimming; the login form cannot produce one, so it counts as a bad request.
    """
    if any(unicodedata.category(character) in REFUSED_NAME_CATEGORIES for character in raw):
        raise RejectedInput("bad_request")
    name = raw.strip()
    if not name:
        raise RejectedInput("name_blank")
    if len(name) > NAME_MAX_LENGTH:
        raise RejectedInput("name_too_long")
    return name


def check_text(raw: str) -> str:
    """Return the message text unchanged, or raise RejectedInput. Length counts code points."""
    if len(raw) > MESSAGE_MAX_LENGTH:
        raise RejectedInput("message_too_long")
    if not raw.strip():
        raise RejectedInput("message_blank")
    return raw


class Room:
    def __init__(
        self,
        *,
        presence_grace: float = PRESENCE_GRACE_SECONDS,
        max_streams: int = MAX_STREAMS,
        max_streams_per_name: int = MAX_STREAMS_PER_NAME,
    ) -> None:
        self.instance = secrets.token_hex(8)
        self._presence_grace = presence_grace
        self._max_streams = max_streams
        self._max_streams_per_name = max_streams_per_name
        self._history: deque[Message] = deque(maxlen=HISTORY_LIMIT)
        self._next_seq = 1
        self._connections: set[Connection] = set()
        self._tabs: dict[str, _PresentTab] = {}

    def post(self, author: str, author_sid: str, html: str) -> Message:
        message = Message(self._next_seq, author, author_sid, html, datetime.now(UTC))
        self._next_seq += 1
        self._history.append(message)
        for connection in self._connections:
            _deliver(connection, message)
        return message

    def connect(self, tab: str, name: str, sid: str, last_event_id: str | None) -> Connection:
        """Register a stream; raises RejectedInput("too_many_streams") at either cap."""
        same_name = sum(1 for open_one in self._connections if open_one.name == name)
        if len(self._connections) >= self._max_streams or same_name >= self._max_streams_per_name:
            raise RejectedInput("too_many_streams")
        before = self._names_key()
        connection = Connection(tab, name, sid, self._replay_after(last_event_id))
        self._connections.add(connection)
        present = self._tabs.setdefault(tab, _PresentTab(name))
        present.name = name
        present.connections.add(connection)
        if present.expiry is not None:
            present.expiry.cancel()
            present.expiry = None
        self._broadcast_presence_if_changed(before, skip=connection)
        return connection

    def disconnect(self, connection: Connection) -> None:
        """Remove a stream; a second call, or one for a tab that left, changes nothing."""
        if connection not in self._connections:
            return
        self._connections.remove(connection)
        present = self._tabs.get(connection.tab)
        if present is None or connection not in present.connections:
            return
        present.connections.remove(connection)
        if not present.connections:
            present.expiry = asyncio.get_running_loop().call_later(
                self._presence_grace, self._expire, connection.tab, present
            )

    def leave(self, tab: str) -> None:
        before = self._names_key()
        present = self._tabs.pop(tab, None)
        if present is None:
            return
        if present.expiry is not None:
            present.expiry.cancel()
        self._broadcast_presence_if_changed(before)

    def names(self) -> list[str]:
        return [present.name for present in self._tabs.values()]

    def _expire(self, tab: str, present: _PresentTab) -> None:
        if self._tabs.get(tab) is present and not present.connections:
            self.leave(tab)

    def _replay_after(self, last_event_id: str | None) -> list[Message]:
        match = LAST_EVENT_ID.fullmatch(last_event_id or "")
        if match is None or match.group(1) != self.instance:
            return list(self._history)
        seen = int(match.group(2))
        return [message for message in self._history if message.seq > seen]

    def _names_key(self) -> list[str]:
        return sorted(self.names())

    def _broadcast_presence_if_changed(
        self, before: list[str], skip: Connection | None = None
    ) -> None:
        if self._names_key() == before:
            return
        presence = Presence(tuple(self.names()))
        for connection in self._connections:
            if connection is not skip:
                _deliver(connection, presence)


def _deliver(connection: Connection, event: RoomEvent) -> None:
    """Queue an event; a full queue marks the stream to end so the browser replays on reconnect."""
    if connection.is_overflowed:
        return
    try:
        connection.queue.put_nowait(event)
    except asyncio.QueueFull:
        connection.is_overflowed = True
