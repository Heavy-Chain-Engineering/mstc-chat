import re
import time

import httpx
import pytest
from starlette.applications import Starlette

from tests.conftest import (
    TAB_A,
    TAB_B,
    AppFactory,
    ClientFactory,
    data_of,
    open_stream,
    room_of,
    sign_in,
)

pytestmark = pytest.mark.anyio


async def test_should_open_with_retry_hello_and_presence_when_room_is_empty(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    cookie = await sign_in(client, "Avery")

    stream = await open_stream(app, cookie)
    events = await stream.events_until("presence")
    await stream.close()

    assert await stream.status == 200
    assert events[0] == {"retry": "1000"}
    assert events[1] == {"event": "hello", "data": f'{{"instance": "{room_of(app).instance}"}}'}
    assert data_of(events[2]) == {"names": ["Avery"]}
    assert re.fullmatch(r"[0-9a-f]{16}", room_of(app).instance)


async def test_should_deliver_post_to_every_open_stream_with_own_flag_ac6(
    make_client: ClientFactory, app: Starlette
) -> None:
    avery, jordan = await make_client(), await make_client()
    avery_stream = await open_stream(app, await sign_in(avery, "Avery"), TAB_A)
    jordan_stream = await open_stream(app, await sign_in(jordan, "Avery"), TAB_B)
    await avery_stream.events_until("presence")
    await jordan_stream.events_until("presence")
    started = time.monotonic()

    await avery.post("/api/messages", json={"text": "hello *class*"})
    seen_by_author = await avery_stream.events_until("message", timeout=2.0)
    seen_by_other = await jordan_stream.events_until("message", timeout=2.0)

    elapsed = time.monotonic() - started
    await avery_stream.close()
    await jordan_stream.close()
    author_view, other_view = data_of(seen_by_author[-1]), data_of(seen_by_other[-1])
    assert elapsed < 2.0
    assert author_view["own"] is True
    assert other_view["own"] is False
    assert other_view["author"] == "Avery"
    assert other_view["html"] == "<p>hello <em>class</em></p>\n"
    assert set(other_view) == {"seq", "author", "html", "receivedAt", "own"}
    assert seen_by_other[-1]["id"] == f"{room_of(app).instance}:1"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", str(other_view["receivedAt"]))


async def test_should_replay_history_oldest_first_when_late_joiner_opens_stream_ac7(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    cookie = await sign_in(client, "Avery")
    await client.post("/api/messages", json={"text": "one"})
    await client.post("/api/messages", json={"text": "two"})

    stream = await open_stream(app, cookie)
    events = await stream.events_until("presence")
    await stream.close()

    kinds = [event.get("event") for event in events]
    assert kinds == [None, "hello", "message", "message", "presence"]
    assert [data_of(event)["seq"] for event in events[2:4]] == [1, 2]


async def test_should_replay_only_later_messages_when_last_event_id_names_this_instance_ac10(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    cookie = await sign_in(client, "Avery")
    await client.post("/api/messages", json={"text": "one"})
    await client.post("/api/messages", json={"text": "two"})

    stream = await open_stream(app, cookie, last_event_id=f"{room_of(app).instance}:1")
    events = await stream.events_until("presence")
    await stream.close()

    assert [data_of(e)["seq"] for e in events if e.get("event") == "message"] == [2]


@pytest.mark.parametrize("last_event_id", ["0123456789abcdef:1", "nonsense"])
async def test_should_replay_all_when_last_event_id_is_foreign_or_malformed_ac10(
    client: httpx.AsyncClient, app: Starlette, last_event_id: str
) -> None:
    cookie = await sign_in(client, "Avery")
    await client.post("/api/messages", json={"text": "one"})
    await client.post("/api/messages", json={"text": "two"})

    stream = await open_stream(app, cookie, last_event_id=last_event_id)
    events = await stream.events_until("presence")
    await stream.close()

    assert [data_of(e)["seq"] for e in events if e.get("event") == "message"] == [1, 2]


async def test_should_end_without_goodbye_and_free_its_slot_when_lifetime_passes(
    make_app: AppFactory,
) -> None:
    app = make_app(stream_lifetime=0.2, max_streams=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        cookie = await sign_in(client, "Avery")
        stream = await open_stream(app, cookie)

        events = await stream.events_until_end(timeout=1.0)
        again = await open_stream(app, cookie)
        await again.close()

    assert [event.get("event") for event in events] == [None, "hello", "presence"]
    assert await again.status == 200


async def test_should_free_its_slot_when_client_disconnects_mid_stream(
    make_app: AppFactory,
) -> None:
    app = make_app(max_streams=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        cookie = await sign_in(client, "Avery")
        first = await open_stream(app, cookie)
        await first.events_until("presence")

        await first.close()
        second = await open_stream(app, cookie)
        await second.close()

    assert await second.status == 200


async def test_should_refuse_extra_stream_but_keep_login_and_posting_when_cap_is_full(
    make_app: AppFactory,
) -> None:
    app = make_app(max_streams=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        cookie = await sign_in(client, "Avery")
        first = await open_stream(app, cookie, TAB_A)

        refused = await client.get(f"/api/stream?tab={TAB_B}")
        login = await client.post(
            "/api/login", json={"name": "Jordan", "password": "correct horse battery staple"}
        )
        post = await client.post("/api/messages", json={"text": "still works"})
        await first.close()

    assert refused.status_code == 429
    assert refused.json() == {"error": "too_many_streams"}
    assert login.status_code == 200
    assert post.status_code == 204


async def test_should_refuse_sixth_stream_when_one_name_has_five_open(
    make_app: AppFactory,
) -> None:
    app = make_app(max_streams_per_name=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        first = await open_stream(app, await sign_in(client, "Avery"), TAB_A)

        refused = await client.get(f"/api/stream?tab={TAB_B}")
        await first.close()

    assert refused.status_code == 429


@pytest.mark.parametrize("query", ["", "?tab=", "?tab=not-a-uuid", f"?tab={TAB_A.upper()}"])
async def test_should_refuse_with_bad_request_when_tab_id_is_missing_or_malformed(
    client: httpx.AsyncClient, app: Starlette, query: str
) -> None:
    await sign_in(client, "Avery")

    response = await client.get(f"/api/stream{query}")

    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert room_of(app).names() == []


async def test_should_drop_tab_from_every_list_when_leave_beacon_arrives_ac9(
    make_client: ClientFactory, app: Starlette
) -> None:
    avery, jordan = await make_client(), await make_client()
    watcher = await open_stream(app, await sign_in(avery, "Avery"), TAB_A)
    await watcher.events_until("presence")
    leaver = await open_stream(app, await sign_in(jordan, "Jordan"), TAB_B)
    joined = await watcher.events_until("presence")

    response = await jordan.post("/api/leave", content=TAB_B)
    left = await watcher.events_until("presence")
    await watcher.close()
    await leaver.close()

    assert response.status_code == 204
    assert sorted(data_of(joined[-1])["names"]) == ["Avery", "Jordan"]
    assert data_of(left[-1]) == {"names": ["Avery"]}


@pytest.mark.parametrize("body", [b"not-a-tab", b"\xff\xfe"])
async def test_should_refuse_with_bad_request_when_leave_body_is_not_a_tab_id(
    client: httpx.AsyncClient, body: bytes
) -> None:
    await sign_in(client, "Avery")

    response = await client.post("/api/leave", content=body)

    assert response.status_code == 400


async def test_should_end_stream_and_replay_rest_on_reconnect_when_200_events_wait_unread(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    cookie = await sign_in(client, "Avery")
    stream = await open_stream(app, cookie)
    await stream.events_until("presence")
    room = room_of(app)

    _ = [room.post("Jordan", "sid-j", f"<p>{n}</p>") for n in range(201)]
    delivered = await stream.events_until_end(timeout=1.0)
    resumed = await open_stream(app, cookie, last_event_id=delivered[-1]["id"])
    replayed = await resumed.events_until("presence")
    await resumed.close()

    delivered_seqs = [data_of(event)["seq"] for event in delivered]
    replayed_seqs = [data_of(e)["seq"] for e in replayed if e.get("event") == "message"]
    assert len(delivered) < 201
    assert delivered_seqs + replayed_seqs == list(range(1, 202))


async def test_should_write_each_event_as_one_ascii_line_when_text_has_newlines_and_unicode(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    cookie = await sign_in(client, "Zoë")
    await client.post("/api/messages", json={"text": "line one\n\nevent: forged\ndata: é"})

    stream = await open_stream(app, cookie)
    events = await stream.events_until("presence")
    await stream.close()

    message = events[2]
    assert set(message) == {"event", "id", "data"}
    assert message["data"].isascii()
    assert data_of(message)["author"] == "Zoë"


async def test_should_end_stream_when_its_queue_of_the_set_size_is_full(
    make_app: AppFactory,
) -> None:
    app = make_app(queue_size=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        cookie = await sign_in(client, "Avery")
        stream = await open_stream(app, cookie)
        await stream.events_until("presence")
        room = room_of(app)

        _ = [room.post("Jordan", "sid-j", f"<p>{n}</p>") for n in range(3)]
        delivered = await stream.events_until_end(timeout=1.0)

    assert [data_of(event)["seq"] for event in delivered] == [1]
