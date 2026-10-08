import asyncio
import json
import time

import httpx
import pytest

from tests.conftest import (
    CLASS_PASSWORD,
    COOKIE_NAME,
    AppFactory,
    ClientFactory,
)

pytestmark = pytest.mark.anyio


async def test_should_answer_cleaned_name_and_set_cookie_when_password_is_right_ac2(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/login", json={"name": "  Avery Sample ", "password": CLASS_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json() == {"name": "Avery Sample"}
    assert client.cookies.get(COOKIE_NAME)


async def test_should_set_host_only_secure_strict_cookie_when_signing_in_ac4(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/login", json={"name": "Avery", "password": CLASS_PASSWORD})

    cookie = response.headers["set-cookie"]
    attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")[1:]}
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert attributes == {"max-age", "path", "secure", "httponly", "samesite"}
    assert "max-age=14400" in cookie.lower()
    assert "path=/;" in cookie.lower()
    assert "samesite=strict" in cookie.lower()


async def test_should_refuse_after_at_least_one_second_without_cookie_when_password_is_wrong_ac2(
    make_app: AppFactory,
) -> None:
    app = make_app(wrong_password_delay=1.0)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        started = time.monotonic()

        response = await client.post("/api/login", json={"name": "Avery", "password": "wrong"})

        elapsed = time.monotonic() - started
    assert response.status_code == 401
    assert response.json() == {"error": "wrong_password"}
    assert elapsed >= 1.0
    assert "set-cookie" not in response.headers


async def test_should_still_sign_in_when_right_password_follows_twenty_wrong_ones_ac2(
    client: httpx.AsyncClient,
) -> None:
    wrong = await asyncio.gather(
        *[
            client.post("/api/login", json={"name": "Avery", "password": f"guess {n}"})
            for n in range(20)
        ]
    )

    response = await client.post("/api/login", json={"name": "Avery", "password": CLASS_PASSWORD})

    assert [answer.status_code for answer in wrong] == [401] * 20
    assert response.status_code == 200


async def test_should_refuse_without_crashing_when_wrong_password_is_not_ascii_ac2(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/login", json={"name": "Avery", "password": "pässwörd ✓ 😀"})

    assert response.status_code == 401
    assert response.json() == {"error": "wrong_password"}


async def test_should_sign_in_when_right_password_is_not_ascii(make_app: AppFactory) -> None:
    app = make_app(class_password="pässwörd ✓ 😀")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        response = await client.post(
            "/api/login", json={"name": "Avery", "password": "pässwörd ✓ 😀"}
        )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("name", "code"),
    [("", "name_blank"), ("   ", "name_blank"), ("a" * 51, "name_too_long")],
)
async def test_should_refuse_without_cookie_when_name_is_blank_or_too_long_ac3(
    client: httpx.AsyncClient, name: str, code: str
) -> None:
    response = await client.post("/api/login", json={"name": name, "password": CLASS_PASSWORD})

    assert response.status_code == 422
    assert response.json() == {"error": code}
    assert "set-cookie" not in response.headers


async def test_should_sign_in_when_name_has_exactly_50_characters_ac3(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/login", json={"name": "ñ" * 50, "password": CLASS_PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"name": "ñ" * 50}


async def test_should_refuse_with_bad_request_when_name_holds_lone_surrogate(
    client: httpx.AsyncClient,
) -> None:
    body = f'{{"name": "Avery\\ud800", "password": "{CLASS_PASSWORD}"}}'

    response = await client.post(
        "/api/login", content=body, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert "set-cookie" not in response.headers


async def test_should_refuse_at_once_with_busy_when_wrong_password_waits_are_full(
    make_app: AppFactory,
) -> None:
    app = make_app(wrong_password_delay=0.3, max_waiting_logins=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        waiting = [
            asyncio.create_task(
                client.post("/api/login", json={"name": "Avery", "password": f"guess {n}"})
            )
            for n in range(2)
        ]
        await asyncio.sleep(0.05)
        started = time.monotonic()

        busy = await client.post("/api/login", json={"name": "Jordan", "password": CLASS_PASSWORD})

        elapsed = time.monotonic() - started
        refused = await asyncio.gather(*waiting)
        after = await client.post("/api/login", json={"name": "Jordan", "password": CLASS_PASSWORD})
    assert busy.status_code == 429
    assert busy.json() == {"error": "busy"}
    assert elapsed < 0.2
    assert [answer.status_code for answer in refused] == [401, 401]
    assert after.status_code == 200


async def test_should_answer_too_large_without_cookie_when_body_is_over_32_kb_ac3(
    client: httpx.AsyncClient,
) -> None:
    body = json.dumps({"name": "Avery", "password": CLASS_PASSWORD, "pad": "x" * 32_768})

    response = await client.post(
        "/api/login", content=body, headers={"content-type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json() == {"error": "too_large"}
    assert "set-cookie" not in response.headers


async def test_should_give_each_participant_own_session_when_two_sign_in(
    make_client: ClientFactory,
) -> None:
    first, second = await make_client(), await make_client()

    await first.post("/api/login", json={"name": "Avery", "password": CLASS_PASSWORD})
    await second.post("/api/login", json={"name": "Jordan", "password": CLASS_PASSWORD})

    assert (await first.get("/api/session")).json() == {"name": "Avery"}
    assert (await second.get("/api/session")).json() == {"name": "Jordan"}


@pytest.mark.parametrize(
    "name",
    ["Avery‮", "Ave​ry", "Avery\n", "\tAvery", "Av\x00ery", "Avery\x7f"],
)
async def test_should_refuse_at_once_with_bad_request_when_name_holds_control_or_format_character(
    make_app: AppFactory, name: str
) -> None:
    app = make_app(wrong_password_delay=1.0)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        started = time.monotonic()

        response = await client.post("/api/login", json={"name": name, "password": CLASS_PASSWORD})

        elapsed = time.monotonic() - started
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert "set-cookie" not in response.headers
    assert elapsed < 0.5


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"name": "Avery"}',
        b'{"name": "Avery", "password": 5}',
        b'{"name": "Avery", "password": "wrong\\ud800"}',
        b'{"name": "Avery", "password": "\xff"}',
    ],
)
async def test_should_refuse_at_once_with_bad_request_when_login_body_is_malformed(
    make_app: AppFactory, body: bytes
) -> None:
    app = make_app(wrong_password_delay=1.0)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        started = time.monotonic()

        response = await client.post(
            "/api/login", content=body, headers={"content-type": "application/json"}
        )

        elapsed = time.monotonic() - started
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert "set-cookie" not in response.headers
    assert elapsed < 0.5
