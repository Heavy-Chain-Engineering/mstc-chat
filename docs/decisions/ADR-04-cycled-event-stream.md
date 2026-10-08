+++
id = "ADR-04"
name = "CYCLED-EVENT-STREAM"
kind = "pattern"
status = "accepted"
decision = "Each open tab holds one Server-Sent Events stream that the server ends after 20 seconds; the browser reconnects with Last-Event-ID, every stream opens with a hello naming the server instance, a page reloads once for each new instance, and presence is kept per tab with a 5-second grace and a leave beacon."
use_when = "Sending anything live from the server to open pages: messages, the online list, a restart."
do_not_use_when = "The browser sends something to the server; that is an ordinary POST route."
use_instead = ["ADR-01"]
applies_to = ["backend/app.py", "backend/room.py", "frontend/src/stream.ts", "frontend/src/room.ts"]
rules = [
  "The stream starts with retry: 1000 and a hello event carrying the instance id, then the replay, then presence; it has no closing event.",
  "The server ends every stream after the stream lifetime (20 s), or at once when the connection's queue (maxsize 200) is full; the stream body calls Room.disconnect in a finally, and Room.disconnect ignores a connection it no longer holds.",
  "Every message event has the id <instance>:<seq>; a Last-Event-ID matching ^[0-9a-f]{16}:[0-9]{1,15}$ and naming this instance replays only later messages; any other value, or a failed parse, counts as no header and replays the whole kept history.",
  "Each message event carries own, true only on the connections whose session sid sent it; no event carries a sid.",
  "The client applies messages by seq and ignores a seq it has already shown for the same instance.",
  "A hello from a new instance makes the client save the unsent draft, a restarted flag and the instance id in sessionStorage and reload, at most once per instance id; after the reload it restores the draft once, deletes the record and shows that the chat restarted.",
  "A hello from an instance the client has already left closes that stream and reconnects after 1 s, with no reload and no notice; after about 10 s of that the client accepts that instance.",
  "The reconnecting notice shows after 3 s down.",
  "A tab stays in the online list while it has an open connection and for 5 seconds after its last one ends; a leave beacon, sent on pagehide when the page is not kept in the back/forward cache, removes it at once.",
  "The room refuses a 151st open connection, or a 6th under one display name, with too_many_streams.",
  "Event data is json.dumps output with its defaults, on one line.",
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
`Last-Event-ID`; each stream opens with a `hello` naming the server instance; a page reloads once
for each new instance; presence is kept per tab with a 5-second grace and a leave beacon.

Ruled by the person on 2026-10-08: the in-class demo redeploys the live room, wipes the history,
and moves every open page to the new version within 30 seconds (gray-areas-spec.md GA-023). The
VP ruled the client behaviour below on the same day (gray-areas-architect.md GA-035 to GA-039).

- `retry: 1000` tells `EventSource` to reconnect 1 second after a stream ends, so the hand-over
  after a redeploy takes about 20 + 1 seconds plus a round trip, inside the 30 seconds.
- With no closing event, the reconnecting notice waits 3 seconds, so the routine reconnect never
  shows it and a real drop does. Removing the connection in a `finally` keeps the room's
  connection set and the online list right however a stream ends.
- A bounded queue keeps a slow reader from growing the server's memory; ending its stream lets
  the browser catch up through the normal replay.
- The `<instance>:<seq>` id lets the browser's own `Last-Event-ID` header carry what the tab last
  saw. The server replays only what it missed; a different instance replays everything it has.
  The digit limit keeps a forged header from costing a huge integer parse.
- De-duplicating by `seq` on the client makes "each missed message once" hold even when a replay
  overlaps what the tab already shows (AC-10).
- The `own` flag lets two people with one name each see only their own messages on their side,
  without sending the `sid` to anyone.
- The instance id is the one restart signal: a new instance means an empty room (AC-10, AC-19).
  Reloading on it loads the new client after the demo deploy. Saving the draft first means a
  student loses nothing; the server never sees that draft. Once per instance id stops a reload
  loop.
- Refusing an instance the page has already left stops a page from flipping back to the old
  revision while Cloud Run hands over; accepting it after about 10 seconds covers a rollback.
- The grace stops the online list from flickering at every planned reconnect. The beacon removes
  a normally closed tab at once (AC-9); a page kept in the back/forward cache sends no beacon and
  reconnects when it comes back. A crashed tab leaves within 20 + 5 seconds.
- The caps keep one participant who knows the password from filling Cloud Run's 250 request slots
  with streams, so logins and posts still get through. A class of 50 with two tabs each stays well
  below them.
- `json.dumps` output is one line, so a newline inside a message cannot start a forged event.

`tests/test_stream.py` runs the app with a 0.2-second lifetime, a small queue and small caps, and
checks the event order, the replay rules, the `own` flag, the full-queue end, the removal of a
stream the client closed, the caps, and delivery between two clients. `frontend/src/room.test.ts`
and `frontend/src/stream.test.ts` check the client side. The VP checks the live redeploy by hand.

## Consequences

Easier:

- One mechanism bounds the redeploy hand-over and the presence delay, over HTTP/1.1, with the
  browser's built-in `EventSource`.
- Tests prove the hand-over with a short lifetime instead of a deploy.

Harder:

- Each tab makes a request every 20 seconds, about 2.5 a second for 50 tabs.
- A message posted during the 1-second reconnect arrives with the replay, up to about 1.5 seconds
  late. During a redeploy, pages on the old revision see new messages only after they switch.
- A real drop shows its notice after 3 seconds, not the 1 second gray-areas-design.md GA-013 set.
- Presence is per tab, so one student with two tabs is listed twice (spec edge case 1).
- A crash restart reloads open pages, as a redeploy does; the draft sits in the tab's
  `sessionStorage` for the moment of the reload.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| Long streams plus a version check every few seconds | Needs a second mechanism for closed tabs, and the request timeout still has to be short. | Request costs that matter at 50 tabs. |
| HTTP/2 end-to-end (Hypercorn, `--use-http2`) | Passes disconnects, but does not move pages after a redeploy; a less common server. | The rehearsal shows 25 seconds for a crashed tab is too long. |
| A separate client build id beside the instance id | Two restart signals, and the page has no trustworthy copy of its own build id. | Server restarts that must not reload pages. |
| A closing `bye` event to suppress the notice | One more event for one timer; the VP chose a 3-second notice instead. | Students reporting that 3 seconds feels too slow. |
| No leave beacon | A normal close would stay listed up to 25 seconds, against AC-9's 2 seconds. | A spec change that accepts the delay. |
| Waiting for an empty message box before reloading | The page could stay on the old client for a long time. | None. |
| WebSockets | Same revision pinning, plus a custom reconnect and replay protocol. | Two-way traffic on one connection. |
