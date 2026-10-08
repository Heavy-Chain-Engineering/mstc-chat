import httpx
import pytest
from starlette.applications import Starlette

from tests.conftest import TAB_A, room_of, sign_in

pytestmark = pytest.mark.anyio


def _kept_html(app: Starlette) -> list[str]:
    return [m.html for m in room_of(app).connect(TAB_A, "Probe", "sid-probe", None).replay]


async def test_should_keep_rendered_html_when_signed_in_participant_posts(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    await sign_in(client, "Avery")

    response = await client.post("/api/messages", json={"text": "**hi** <script>x</script>"})

    assert response.status_code == 204
    assert _kept_html(app) == ["<p><strong>hi</strong> &lt;script&gt;x&lt;/script&gt;</p>\n"]


async def test_should_accept_message_when_it_has_exactly_4000_code_points_ac7(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    await sign_in(client, "Avery")

    response = await client.post("/api/messages", json={"text": "é" * 4000})

    assert response.status_code == 204
    assert len(_kept_html(app)) == 1


async def test_should_refuse_with_message_too_long_when_message_has_4001_code_points_ac7(
    client: httpx.AsyncClient, app: Starlette
) -> None:
    await sign_in(client, "Avery")

    response = await client.post("/api/messages", json={"text": "a" * 4001})

    assert response.status_code == 422
    assert response.json() == {"error": "message_too_long"}
    assert _kept_html(app) == []


@pytest.mark.parametrize(
    ("text", "code"), [("  \n ", "message_blank"), ("[x]: https://a.b", "message_blank")]
)
async def test_should_refuse_when_message_is_blank_or_renders_empty(
    client: httpx.AsyncClient, app: Starlette, text: str, code: str
) -> None:
    await sign_in(client, "Avery")

    response = await client.post("/api/messages", json={"text": text})

    assert response.status_code == 422
    assert response.json() == {"error": code}
    assert _kept_html(app) == []


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[1, 2]",
        b'{"text": 5}',
        b"{}",
        b'{"text": "hi\\udc00"}',
        b'{"text": "\xff\xfe"}',
        b"[" * 5000 + b"]" * 5000,
    ],
)
async def test_should_refuse_with_bad_request_when_body_is_not_a_json_object_of_strings(
    client: httpx.AsyncClient, app: Starlette, body: bytes
) -> None:
    await sign_in(client, "Avery")

    response = await client.post(
        "/api/messages", content=body, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert _kept_html(app) == []
