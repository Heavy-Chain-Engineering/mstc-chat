import time

import pytest
from itsdangerous import URLSafeTimedSerializer

from backend import session
from backend.session import SESSION_MAX_AGE_SECONDS, Session

SECRET = "s" * 32
OTHER_SECRET = "o" * 32


def test_should_read_back_name_and_sid_when_token_is_fresh() -> None:
    issued = session.new_session("Avery")

    token = session.issue(issued, SECRET)

    assert session.read(token, SECRET) == Session(name="Avery", sid=issued.sid)


def test_should_give_each_sign_in_its_own_random_sid_when_names_match() -> None:
    first, second = session.new_session("Avery"), session.new_session("Avery")

    assert first.sid != second.sid
    assert len(first.sid) >= 16


def test_should_read_none_when_token_is_missing() -> None:
    assert session.read(None, SECRET) is None


def test_should_read_none_when_token_is_older_than_four_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed_at = time.time() - SESSION_MAX_AGE_SECONDS - 1
    monkeypatch.setattr(time, "time", lambda: signed_at)
    token = session.issue(session.new_session("Avery"), SECRET)
    monkeypatch.undo()

    assert session.read(token, SECRET) is None


def test_should_read_session_when_token_is_just_under_four_hours_old(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed_at = time.time() - SESSION_MAX_AGE_SECONDS + 60
    monkeypatch.setattr(time, "time", lambda: signed_at)
    token = session.issue(session.new_session("Avery"), SECRET)
    monkeypatch.undo()

    assert session.read(token, SECRET) is not None


def test_should_read_none_when_token_was_altered() -> None:
    token = session.issue(session.new_session("Avery"), SECRET)
    # The last base64 character can carry only padding bits, so alter one near the start.
    altered = token[0] + ("A" if token[1] != "A" else "B") + token[2:]

    assert session.read(altered, SECRET) is None


def test_should_read_none_when_token_was_signed_with_another_key() -> None:
    token = session.issue(session.new_session("Avery"), OTHER_SECRET)

    assert session.read(token, SECRET) is None


def test_should_read_none_when_token_is_not_a_token() -> None:
    assert session.read("not-a-token", SECRET) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Avery"},
        {"name": "Avery", "sid": 7},
        {"name": 7, "sid": "abc"},
        {"name": "Avery", "sid": ""},
        {"name": "Avery", "sid": "abc", "role": "lecturer"},
        {"name": "   ", "sid": "abc"},
        {"name": "a" * 51, "sid": "abc"},
        ["Avery", "abc"],
        "Avery",
    ],
)
def test_should_read_none_when_signed_payload_has_wrong_shape(payload: object) -> None:
    token = URLSafeTimedSerializer(SECRET, salt=session.SALT).dumps(payload)

    assert session.read(token, SECRET) is None
