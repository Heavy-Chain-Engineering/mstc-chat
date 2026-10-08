+++
id = "ADR-02"
name = "FRAMEWORK-FREE-ROOM-CORE"
kind = "boundary"
status = "proposed"
decision = "Only backend/app.py imports Starlette and only backend/__main__.py imports uvicorn; room.py, session.py and safe_markdown.py import no web framework."
use_when = "Adding a room rule, a limit, a validation, presence logic, session logic or rendering logic."
do_not_use_when = "Adding an HTTP route, a header, a middleware or anything that reads a request or writes a response."
use_instead = ["ADR-01"]
applies_to = ["backend/"]
rules = [
  "backend/room.py imports only the standard library.",
  "session.py and safe_markdown.py import their own library, the standard library and room.py, never starlette or uvicorn.",
  "Room methods take and return plain values and dataclasses; HTTP status codes and event-stream text are made in app.py.",
  "A rejected input raises room.RejectedInput with an error code; app.py turns the code into a status and a JSON body.",
  "pyproject.toml bans starlette and uvicorn with ruff's TID251 and exempts only backend/app.py, backend/__main__.py and tests/**.",
]
example = "backend/room.py"
enforced_by = "ruff rule TID251 (pyproject.toml, [tool.ruff.lint.flake8-tidy-imports.banned-api]), run by the check `uv run ruff check backend tests`"
+++

# ADR-02: The room's rules do not know about HTTP

## Context

The app doubles as the lecture's worked example, so a student should be able to read the chat
room's rules (limits, history, who is online) without reading web-framework code. When rules sit
inside route functions, a test of one rule needs an HTTP request, and the rule cannot be read or
changed without the route around it.

## Decision

Only `backend/app.py` imports Starlette and only `backend/__main__.py` imports uvicorn; the room,
session and Markdown modules import no web framework.

- Keeping `room.py` to the standard library lets `tests/test_room.py` call a rule directly and
  check the result in milliseconds.
- Plain values in and out keep the HTTP vocabulary (status codes, headers, event-stream text) in
  one file, which is the one file a reader opens to see the API.
- A single exception type with an error code gives `app.py` one place to map rule failures to
  responses, and gives the client the stable codes it maps to wording.
- Ruff already runs in the project's checks. Its banned-import rule TID251 flags
  `import starlette...`, `from starlette... import`, `import uvicorn...` and
  `from uvicorn import` in any file without an exemption, and its message names this record.
  It does not see `importlib.import_module("starlette")`; code review covers that. INV-001 runs
  the same rule.

## Consequences

Easier:

- Each rule is tested without HTTP.
- A reader finds every route in one file and every rule in another.
- The boundary costs one lint setting, not a test.

Harder:

- `app.py` has to translate between the room's dataclasses and JSON or event-stream text.
- A per-file exemption covers every banned import, so code review checks that `app.py` does not
  start uvicorn.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| Rules inside the route functions | Rules become testable only through HTTP. | None expected. |
| A service layer with interfaces between app and room | One implementation of each; an interface would add indirection with no second case. | A second real implementation, such as a shared store for more than one instance. |
| A test that imports the core modules and inspects `sys.modules` | Project code that polices a rule the project's linter already expresses (engineering-judgment.md, section 2). | A boundary ruff cannot express. |
| import-linter | A new tool for one rule. | Several layered boundaries to police. |
