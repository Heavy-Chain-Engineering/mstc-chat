import logging
from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette

from backend.__main__ import main
from tests.conftest import (
    CLASS_PASSWORD,
    COOKIE_NAME,
    SESSION_SECRET,
    TAB_A,
    TAB_B,
    AppFactory,
    ClientFactory,
    open_stream,
)

pytestmark = pytest.mark.anyio

NAME = "Privacy Probe Quinn"
MESSAGE = "privacy probe message 7f3a9c"


async def _every_path(make_client: ClientFactory, app: Starlette) -> str:
    """Runs each success and failure path of login, send, stream and leave; returns the cookie."""
    client, stranger = await make_client(), await make_client()
    await client.post("/api/login", json={"name": NAME, "password": "wrong " + NAME})
    await client.post("/api/login", json={"name": NAME + "x" * 50, "password": CLASS_PASSWORD})
    await client.post("/api/login", json={"name": NAME, "password": CLASS_PASSWORD})
    cookie = client.cookies[COOKIE_NAME]
    stream = await open_stream(app, cookie, TAB_A)
    await client.post("/api/messages", json={"text": MESSAGE})
    await client.post("/api/messages", json={"text": MESSAGE * 200})
    await client.post("/api/messages", content=b"{" + MESSAGE.encode())
    await stranger.post("/api/messages", json={"text": MESSAGE})
    await stranger.get(f"/api/stream?tab={TAB_B}", headers={"cookie": f"{COOKIE_NAME}={cookie}x"})
    await stream.events_until("message")
    await client.post("/api/leave", content=TAB_A)
    await client.post("/api/leave", content="not-a-tab " + NAME)
    await stream.close()
    await client.get("/api/session")
    return cookie


async def test_should_log_and_print_no_personal_data_or_secret_on_any_path_ac15(
    make_client: ClientFactory,
    app: Starlette,
    static_dir: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)

    cookie = await _every_path(make_client, app)
    main(
        {"CLASS_PASSWORD": CLASS_PASSWORD, "SESSION_SECRET": SESSION_SECRET},
        run=lambda *args, **kwargs: None,
        static_dir=static_dir,
    )
    main({"CLASS_PASSWORD": CLASS_PASSWORD, "SESSION_SECRET": "x"}, static_dir=static_dir)

    output = capsys.readouterr()
    recorded = caplog.text + output.out + output.err
    assert "MSTC Chat listening" in output.out
    assert [
        value
        for value in (NAME, MESSAGE, CLASS_PASSWORD, SESSION_SECRET, cookie)
        if value in recorded
    ] == []


async def test_should_keep_names_and_messages_only_in_a_new_rooms_memory_when_app_restarts_ac15(
    make_client: ClientFactory, app: Starlette, make_app: AppFactory
) -> None:
    client = await make_client()
    await client.post("/api/login", json={"name": NAME, "password": CLASS_PASSWORD})
    await client.post("/api/messages", json={"text": MESSAGE})
    restarted = make_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="https://testserver"
    ) as fresh:
        stream = await open_stream(restarted, client.cookies[COOKIE_NAME])
        events = await stream.events_until("presence")
        await stream.close()
        session = await fresh.get(
            "/api/session", headers={"cookie": f"{COOKIE_NAME}={client.cookies[COOKIE_NAME]}"}
        )

    assert [event.get("event") for event in events] == [None, "hello", "presence"]
    assert session.json() == {"name": NAME}
