+++
id = "ADR-01"
name = "STARLETTE-UVICORN-SERVER"
kind = "technology"
status = "accepted"
decision = "The server is one Starlette app run by uvicorn in one process with one worker, so all room state lives on one asyncio event loop."
use_when = "Adding or changing anything the Python server does over HTTP: routes, the event stream, static files, start-up."
do_not_use_when = "Writing the room's rules, the session token or Markdown rendering, which stay free of the web framework."
use_instead = ["ADR-02"]
applies_to = ["backend/"]
rules = [
  "backend/__main__.py starts uvicorn with the app object, not an import string, so uvicorn cannot start a second worker.",
  "The server listens on 0.0.0.0 and the port in PORT (default 8080).",
  "Room state is touched only on the event loop: no threads, no executors, no second process.",
  "Timers use the running loop's call_later; nothing starts a background loop.",
  "uvicorn's access log is off; the server sets a 5-second graceful shutdown.",
]
example = "backend/__main__.py"
enforced_by = "tests/test_main.py"
+++

# ADR-01: One Starlette app on uvicorn, one process

## Context

The chat room keeps every message and every open stream in memory, and Cloud Run runs one
instance (DOMAIN.md, design implications 2 and 6). The server must hold about 100 open
Server-Sent Events streams at once and also answer posts. Python's standard library has
`http.server`, but its documentation warns that it is not for production use, and it would need
one thread per open stream and hand-written routing. Two processes or workers would each hold a
different room, so participants would stop seeing each other's messages.

## Decision

The server is one Starlette app run by uvicorn in one process with one worker.

Ruled by the person on 2026-10-08: the person ratified this choice of technology.

- Passing the app object to `uvicorn.run` makes a second worker impossible: uvicorn needs an
  import string to start workers, so the mistake fails at start-up instead of splitting the room.
- One event loop means `Room.post` runs to the end before any other code touches the room, so
  the room needs no lock. A thread or executor would break that.
- `0.0.0.0` and `PORT` are what Cloud Run's container contract asks for.
- The access log would repeat Cloud Run's own request logs; turning it off keeps the app's output
  to start-up and errors, which `tests/test_privacy.py` checks for personal data.
- A 5-second graceful shutdown fits inside Cloud Run's 10 seconds between SIGTERM and SIGKILL.

`tests/test_main.py` checks that the entry point calls uvicorn with the app object, the host and
the port.

## Consequences

Easier:

- Routes, streaming responses and static files are a few readable lines each.
- Tests drive the real app through httpx's `ASGITransport` with no server running.

Harder:

- Two runtime dependencies to keep current; Dependabot already watches `uv`.
- The app cannot use more than one CPU core. At 50 participants it needs a small fraction of one.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| Standard library `http.server` with threads | Not meant for production, one thread per stream, routing and body parsing by hand. | A rule that the app must have no dependencies at all. |
| FastAPI | Adds Pydantic and dependency injection the app does not need; it is Starlette underneath. | Many JSON endpoints with complex payloads. |
| Flask with gevent, or Django | Synchronous by default; streaming many long requests needs extra workers or a different server. | None for this app. |
| Hypercorn instead of uvicorn | Speaks HTTP/2 cleartext, which would pass client disconnects through Cloud Run, but it is less widely used; ADR-04 bounds disconnects without it. | The rehearsal or the live redeploy shows the presence bound or the hand-over is too slow. |
