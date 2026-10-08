import json
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from starlette.applications import Starlette

from backend import session
from tests.conftest import (
    CLASS_PASSWORD,
    COOKIE_NAME,
    INDEX_HTML,
    SESSION_SECRET,
    TAB_A,
    ClientFactory,
    room_of,
    sign_in,
)

pytestmark = pytest.mark.anyio

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def _expired_token(monkeypatch: pytest.MonkeyPatch) -> str:
    signed_at = time.time() - session.SESSION_MAX_AGE_SECONDS - 1
    monkeypatch.setattr(time, "time", lambda: signed_at)
    token = session.issue(session.new_session("Avery"), SESSION_SECRET)
    monkeypatch.undo()
    return token


def _altered_token() -> str:
    token = session.issue(session.new_session("Avery"), SESSION_SECRET)
    # The last base64 character can carry only padding bits, so alter one near the start.
    return token[0] + ("A" if token[1] != "A" else "B") + token[2:]


def _other_key_token() -> str:
    return session.issue(session.new_session("Avery"), "another-secret-of-32-characters!!")


@pytest.fixture(params=["missing", "expired", "altered", "other key"])
def bad_cookie(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str | None:
    tokens = {
        "missing": None,
        "expired": _expired_token(monkeypatch),
        "altered": _altered_token(),
        "other key": _other_key_token(),
    }
    return tokens[request.param]


ROUTES = [
    ("GET", "/api/session", None),
    ("POST", "/api/messages", {"json": {"text": "hello"}}),
    ("GET", f"/api/stream?tab={TAB_A}", None),
    ("POST", "/api/leave", {"content": TAB_A}),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
async def test_should_answer_signed_out_when_cookie_is_missing_expired_altered_or_foreign_ac4(
    client: httpx.AsyncClient,
    app: Starlette,
    bad_cookie: str | None,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    headers = {} if bad_cookie is None else {"cookie": f"{COOKIE_NAME}={bad_cookie}"}

    response = await client.request(method, path, headers=headers, **(body or {}))

    assert response.status_code == 401
    assert response.json() == {"error": "signed_out"}
    assert room_of(app).names() == []


async def test_should_answer_name_when_session_cookie_is_valid(client: httpx.AsyncClient) -> None:
    await sign_in(client, "Avery")

    response = await client.get("/api/session")

    assert response.status_code == 200
    assert response.json() == {"name": "Avery"}


async def test_should_serve_index_without_caching_when_root_is_requested(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


async def test_should_serve_built_asset_when_it_exists(client: httpx.AsyncClient) -> None:
    response = await client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('app');"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/assets/missing.js"),
        ("GET", "/brand/logo.svg"),
        ("POST", "/api/upload"),
        ("GET", "/index.html.bak"),
    ],
)
async def test_should_answer_not_found_when_path_is_no_route(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/"),
        ("GET", "/assets/app.js"),
        ("GET", "/api/session"),
        ("POST", "/api/login"),
        ("GET", "/no-such-page"),
    ],
)
async def test_should_send_security_headers_when_any_response_is_written(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)

    assert response.headers["content-security-policy"] == EXPECTED_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/login", {"json": {"name": "Avery", "password": CLASS_PASSWORD}}),
        ("/api/messages", {"json": {"text": "hello"}}),
        ("/api/leave", {"content": TAB_A}),
    ],
)
async def test_should_refuse_with_cross_site_when_post_comes_from_another_site(
    make_client: ClientFactory, app: Starlette, path: str, body: dict[str, object]
) -> None:
    client = await make_client()
    await sign_in(client, "Jordan")

    response = await client.post(path, headers={"sec-fetch-site": "cross-site"}, **body)

    assert response.status_code == 403
    assert response.json() == {"error": "cross_site"}


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
async def test_should_accept_post_when_fetch_site_is_not_cross_site(
    client: httpx.AsyncClient, site: str
) -> None:
    await sign_in(client, "Avery")

    response = await client.post(
        "/api/messages", json={"text": "hello"}, headers={"sec-fetch-site": site}
    )

    assert response.status_code == 204


async def test_should_change_nothing_when_message_body_is_over_32_kb_ac3(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    await sign_in(client, "Avery")
    body = json.dumps({"text": "hello", "pad": "x" * 32_768})

    response = await client.post(
        "/api/messages", content=body, headers={"content-type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json() == {"error": "too_large"}
    assert room_of(app).connect(TAB_A, "Probe", "sid-probe", None).replay == []


async def test_should_answer_too_large_when_chunked_body_passes_32_kb_without_length_ac3(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    await sign_in(client, "Avery")

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"text": "hello", "pad": "'
        yield b"x" * 40_000
        yield b'"}'

    response = await client.post(
        "/api/messages", content=chunks(), headers={"content-type": "application/json"}
    )

    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert room_of(app).connect(TAB_A, "Probe", "sid-probe", None).replay == []


async def test_should_read_body_when_it_is_exactly_32_768_bytes_ac3(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    await sign_in(client, "Avery")
    start = '{"text": "hello", "pad": "'
    body = start + "x" * (32_768 - len(start) - 2) + '"}'

    response = await client.post(
        "/api/messages", content=body, headers={"content-type": "application/json"}
    )

    assert len(body.encode()) == 32_768
    assert response.status_code == 204
    assert len(room_of(app).connect(TAB_A, "Probe", "sid-probe", None).replay) == 1
