"""The signed session token in the __Host-session cookie (ADR-03).

The token holds the display name and a random session id (`sid`) made at sign-in. The browser
never sees the sid by itself; the server uses it to mark a participant's own messages.
"""

import secrets
from dataclasses import dataclass

from itsdangerous import BadData, URLSafeTimedSerializer

from backend.room import RejectedInput, clean_name

SESSION_MAX_AGE_SECONDS = 14_400
SALT = "mstc-chat-session"
_SID_BYTES = 16


@dataclass(frozen=True)
class Session:
    name: str
    sid: str


def new_session(name: str) -> Session:
    return Session(name=name, sid=secrets.token_urlsafe(_SID_BYTES))


def issue(session: Session, secret: str) -> str:
    return URLSafeTimedSerializer(secret, salt=SALT).dumps(
        {"name": session.name, "sid": session.sid}
    )


def read(token: str | None, secret: str) -> Session | None:
    """Return the token's session, or None when it is missing, expired, altered or malformed."""
    if token is None:
        return None
    try:
        payload: object = URLSafeTimedSerializer(secret, salt=SALT).loads(
            token, max_age=SESSION_MAX_AGE_SECONDS
        )
    except BadData:
        return None
    return _session_from(payload)


def _session_from(payload: object) -> Session | None:
    if not isinstance(payload, dict) or set(payload) != {"name", "sid"}:
        return None
    name, sid = payload["name"], payload["sid"]
    if not isinstance(name, str) or not isinstance(sid, str) or not sid:
        return None
    try:
        return Session(name=clean_name(name), sid=sid)
    except RejectedInput:
        return None
