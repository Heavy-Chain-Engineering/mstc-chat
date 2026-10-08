+++
id = "ADR-03"
name = "SIGNED-SESSION-COOKIE"
kind = "technology"
status = "proposed"
decision = "A session is an itsdangerous URLSafeTimedSerializer token holding the display name, in a __Host-session cookie that the server accepts for 4 hours from sign-in, with no server-side store."
use_when = "Signing a participant in, reading who sent a request, or ending sessions."
do_not_use_when = "Checking the class password itself, which is a constant-time comparison in app.py."
use_instead = ["ADR-01"]
applies_to = ["backend/session.py", "backend/app.py"]
rules = [
  "Only backend/session.py imports itsdangerous; it signs with SESSION_SECRET and a fixed salt.",
  "Reading a token checks its signature, an age of at most 14,400 seconds, a payload of exactly {\"name\": str} and a name that room.clean_name accepts; anything else reads as ended.",
  "The cookie is named __Host-session and set with Path=/, Secure, HttpOnly, SameSite=Strict, Max-Age=14400 and no Domain.",
  "The server never renews a token; a new sign-in issues a new one.",
  "No token, cookie value or secret appears in a log, an error message or a URL.",
]
example = "backend/session.py"
enforced_by = "tests/test_session.py"
+++

# ADR-03: Sessions are signed, timed tokens in a cookie

## Context

The app has no database, so it cannot keep a session table. A participant's browser must still
prove, on every request, that it passed the login, and say which display name it chose (AC-4).
A cookie anyone can edit would let a student post under any name or skip the password. Signing
such a token by hand means choosing an encoding, a signature layout and an expiry check, and each
of those is a place to get security wrong.

## Decision

A session is an itsdangerous `URLSafeTimedSerializer` token holding the display name, in a
`__Host-session` cookie that the server accepts for 4 hours from sign-in, with no server store.

- One module owns the library so that a reader sees the whole session logic in one place.
- The age check uses the timestamp inside the signed token, which is the server-enforced absolute
  timeout OWASP asks for; the cookie's own `Max-Age` only tidies the browser.
- The `__Host-` prefix makes browsers refuse the cookie unless it is `Secure`, has `Path=/` and no
  `Domain`, so another site under `run.app` cannot set or overwrite it.
- Re-checking the payload and the name means a token from an earlier build, whose rules may
  have differed, is refused rather than raising an error.
- No renewal keeps the 4-hour limit the person ruled (gray-areas-spec.md GA-021).
- Changing `SESSION_SECRET` and redeploying ends every session at once; that is the only
  revocation, which suits one lecture.

## Consequences

Easier:

- No store; any instance with the same secret accepts the cookie, so a restart keeps people
  signed in.
- A tampered, foreign-key or old token fails one check in one function.

Harder:

- One more dependency.
- A single session cannot be revoked before it expires.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| Hand-written HMAC with `hmac` and `base64` | Every format and expiry choice would be custom security code. | A rule that the server have no third-party dependency. |
| Starlette's `SessionMiddleware` | It re-signs the cookie on every response, which makes the 4-hour limit slide. | None for this app. |
| A JWT library | A larger standard for one name and a timestamp. | Tokens that other services must read. |
| Server-side sessions in memory | A restart would sign everyone out, and the store adds code. | A need to revoke one session. |
