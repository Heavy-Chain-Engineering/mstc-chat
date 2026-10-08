+++
id = "ADR-04"
name = "CYCLED-EVENT-STREAM"
kind = "pattern"
status = "proposed"
decision = "Each open tab holds one Server-Sent Events stream that the server ends after 20 seconds; the browser reconnects with Last-Event-ID, every stream opens with a hello naming the server instance, and presence is kept per tab with a 5-second grace and a leave beacon."
use_when = "Sending anything live from the server to open pages: messages, the online list, a restart."
do_not_use_when = "The browser sends something to the server; that is an ordinary POST route."
use_instead = ["ADR-01"]
applies_to = ["backend/app.py", "backend/room.py", "frontend/src/stream.ts", "frontend/src/room.ts"]
rules = [
  "The stream starts with retry: 1000 and a hello event carrying the instance id, then the replay, then presence.",
  "The server ends every stream after the stream lifetime (20 s) with a bye event; the stream body calls Room.disconnect in a finally, and Room.disconnect ignores a connection it no longer holds.",
  "Every message event has the id <instance>:<seq>; a Last-Event-ID matching ^[0-9a-f]{16}:[0-9]{1,9}$ and naming this instance replays only later messages, any other value replays the whole kept history.",
  "The client applies messages by seq and ignores a seq it has already shown for the same instance.",
  "A hello with a new instance empties the client's room; the page then reloads once its message box is empty and no send is in flight, at most once per 30 s per tab, and stores nothing in the browser but the time of that reload.",
  "A tab stays in the online list while it has an open connection and for 5 seconds after its last one ends; a leave beacon, sent on pagehide when the page is not kept in the back/forward cache, removes it at once.",
  "The room refuses a 151st open connection, or a 6th under one display name, with too_many_streams.",
  "Event data is one line of JSON.",
]
example = "backend/app.py"
enforced_by = "tests/test_stream.py"
+++

# ADR-04: Streams end every 20 seconds and say which server sent them

## Context

Cloud Run keeps a request that is in progress on the revision that started it, even after a
redeploy moves all traffic to a new revision (research R29). A Server-Sent Events stream is one
long request, so after the in-class redeploy the open pages would stay in the old room until the
request timeout ends their streams, while new posts reach the new room (AC-19 asks for at most 30
seconds). Over HTTP/1.1, Cloud Run also does not tell the container when a browser closes a tab
(R32), so a closed tab would stay in the online list until its stream ends (AC-9). Both problems
come from streams that live too long.

## Decision

Each tab holds one stream that the server ends after 20 seconds; the browser reconnects with
`Last-Event-ID`; each stream opens with a `hello` naming the server instance; presence is kept
per tab with a 5-second grace and a leave beacon.

- `retry: 1000` tells `EventSource` to reconnect 1 second after a stream ends, so the hand-over
  after a redeploy takes about 20 + 1 seconds plus a round trip, inside the 30 seconds.
- The planned `bye` lets the client tell a scheduled reconnect from a dropped connection, so the
  reconnecting notice appears only for real drops. Removing the connection in a `finally` keeps
  the room's connection set and the online list right however a stream ends.
- The `<instance>:<seq>` id lets the browser's own `Last-Event-ID` header carry what the tab last
  saw. The server replays only what it missed; a different instance replays everything it has.
  The digit limit keeps a forged header from costing a huge integer parse.
- De-duplicating by `seq` on the client makes "each missed message once" hold even when a
  replay overlaps what the tab already shows (AC-10).
- The instance id is the restart signal the design asked for: a new instance means an empty
  room (AC-10, AC-19). Reloading on it also loads the new client after the demo deploy
  (gray-areas-spec.md GA-023). Waiting for an empty message box keeps a student's draft without
  storing it, and the 30-second guard stops a reload loop if a page alternates between two
  instances.
- The grace stops the online list from flickering at every planned reconnect. The beacon
  removes a normally closed tab at once (AC-9); a page kept in the back/forward cache sends no
  beacon and reconnects when it comes back. A crashed tab leaves within 20 + 5 seconds.
- The caps keep one participant who knows the password from filling Cloud Run's 250 request
  slots with streams, so logins and posts still get through. A class of 50 with two tabs each
  stays well below them.
- One-line JSON means a newline inside a message cannot start a forged event.

`tests/test_stream.py` runs the app with a 0.2-second lifetime and small caps and checks the
event order, the `bye`, the replay rules, the removal of a stream the client closed, the caps,
and delivery between two clients. `frontend/src/room.test.ts` and `frontend/src/stream.test.ts`
check the client side.

## Consequences

Easier:

- One mechanism bounds the redeploy hand-over and the presence delay, over HTTP/1.1, with the
  browser's built-in `EventSource`.
- Tests prove the hand-over with a short lifetime instead of a deploy.

Harder:

- Each tab makes a request every 20 seconds, about 2.5 a second for 50 tabs.
- A message posted during the 1-second reconnect arrives with the replay, up to about 1.5 seconds
  late. During a redeploy, pages on the old revision see new messages only after they switch.
- Presence is per tab, so one student with two tabs is listed twice (spec edge case 1).
- A crash restart reloads open pages, as a redeploy does.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| Long streams plus a version check every few seconds | Needs a second mechanism for closed tabs, and the request timeout still has to be short. | Request costs that matter at 50 tabs. |
| HTTP/2 end-to-end (Hypercorn, `--use-http2`) | Passes disconnects, but does not move pages after a redeploy; a less common server. | The rehearsal shows 25 seconds for a crashed tab is too long. |
| A separate client build id beside the instance id | Two restart signals, and the page has no trustworthy copy of its own build id. | Server restarts that must not reload pages. |
| No leave beacon | A normal close would stay listed up to 25 seconds, against AC-9's 2 seconds. | A spec change that accepts the delay. |
| Saving the draft in `sessionStorage` before a reload | Stores message text in the browser, against AC-15's memory-only rule. | None. |
| WebSockets | Same revision pinning, plus a custom reconnect and replay protocol. | Two-way traffic on one connection. |
