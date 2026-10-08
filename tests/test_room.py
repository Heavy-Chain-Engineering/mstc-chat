import asyncio
import re
from datetime import UTC

import pytest

from backend.room import (
    Connection,
    Message,
    Presence,
    RejectedInput,
    Room,
    check_text,
    clean_name,
)

pytestmark = pytest.mark.anyio

TAB_A = "00000000-0000-4000-8000-00000000000a"
TAB_B = "00000000-0000-4000-8000-00000000000b"
TAB_C = "00000000-0000-4000-8000-00000000000c"


def tab_id(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def test_should_replay_only_newest_200_oldest_first_when_late_joiner_connects() -> None:
    room = Room()
    for number in range(1, 206):
        room.post("Avery", "sid-avery", f"<p>post {number}</p>")

    connection = room.connect(TAB_A, "Jordan", "sid-jordan", None)

    assert [message.seq for message in connection.replay] == list(range(6, 206))
    assert connection.replay[0].html == "<p>post 6</p>"
    assert connection.replay[-1].html == "<p>post 205</p>"


def test_should_number_messages_from_one_in_arrival_order_when_posted() -> None:
    room = Room()

    first = room.post("Avery", "sid-avery", "<p>one</p>")
    second = room.post("Jordan", "sid-jordan", "<p>two</p>")

    assert (first.seq, second.seq) == (1, 2)
    assert (first.author, first.author_sid, first.html) == ("Avery", "sid-avery", "<p>one</p>")
    assert first.received_at.tzinfo is UTC
    assert second.received_at >= first.received_at


def test_should_give_each_room_its_own_hex_instance_when_created() -> None:
    first, second = Room(), Room()

    assert re.fullmatch(r"[0-9a-f]{16}", first.instance)
    assert first.instance != second.instance


def test_should_deliver_every_message_to_each_of_50_connections_when_posted() -> None:
    room = Room()
    connections = [room.connect(tab_id(n), f"Student {n}", f"sid-{n}", None) for n in range(50)]
    _ = [_drain(connection) for connection in connections]

    room.post("Avery", "sid-avery", "<p>one</p>")
    room.post("Avery", "sid-avery", "<p>two</p>")

    received = [[m.seq for m in _messages(_drain(connection))] for connection in connections]
    assert received == [[1, 2]] * 50


def test_should_replay_only_later_messages_when_last_event_id_names_this_instance() -> None:
    room = Room()
    for number in range(1, 6):
        room.post("Avery", "sid-avery", f"<p>{number}</p>")

    connection = room.connect(TAB_A, "Jordan", "sid-jordan", f"{room.instance}:3")

    assert [message.seq for message in connection.replay] == [4, 5]


@pytest.mark.parametrize(
    "last_event_id",
    [
        "0123456789abcdef:3",
        "garbage",
        "",
        "{instance}:1234567890123456",
        "{instance}:-1",
        "{instance}:3 ",
    ],
)
def test_should_replay_whole_history_when_last_event_id_is_foreign_or_malformed(
    last_event_id: str,
) -> None:
    room = Room()
    for number in range(1, 6):
        room.post("Avery", "sid-avery", f"<p>{number}</p>")

    connection = room.connect(
        TAB_A, "Jordan", "sid-jordan", last_event_id.format(instance=room.instance)
    )

    assert [message.seq for message in connection.replay] == [1, 2, 3, 4, 5]


def test_should_accept_fifteen_digit_sequence_when_last_event_id_names_this_instance() -> None:
    room = Room()
    room.post("Avery", "sid-avery", "<p>1</p>")

    connection = room.connect(TAB_A, "Jordan", "sid-jordan", f"{room.instance}:999999999999999")

    assert connection.replay == []


def test_should_trim_surrounding_whitespace_when_name_is_clean() -> None:
    assert clean_name("  Avery Sample \u3000") == "Avery Sample"


def test_should_accept_fifty_characters_when_name_is_at_the_limit() -> None:
    assert clean_name("é" * 50) == "é" * 50


@pytest.mark.parametrize("raw", ["", "   ", "　"])
def test_should_refuse_with_name_blank_when_name_is_only_whitespace(raw: str) -> None:
    with pytest.raises(RejectedInput) as refusal:
        clean_name(raw)

    assert refusal.value.code == "name_blank"


def test_should_refuse_with_name_too_long_when_name_has_51_characters_after_trim() -> None:
    with pytest.raises(RejectedInput) as refusal:
        clean_name(" " + "a" * 51 + " ")

    assert refusal.value.code == "name_too_long"


def test_should_return_text_unchanged_when_message_has_4000_code_points() -> None:
    text = "😀" * 4000

    assert check_text(text) == text


def test_should_refuse_with_message_too_long_when_message_has_4001_code_points() -> None:
    with pytest.raises(RejectedInput) as refusal:
        check_text("a" * 4001)

    assert refusal.value.code == "message_too_long"


@pytest.mark.parametrize("raw", ["", " ", "\n\t "])
def test_should_refuse_with_message_blank_when_message_is_only_whitespace(raw: str) -> None:
    with pytest.raises(RejectedInput) as refusal:
        check_text(raw)

    assert refusal.value.code == "message_blank"


def test_should_refuse_151st_connection_when_150_streams_are_open() -> None:
    room = Room()
    for number in range(150):
        room.connect(tab_id(number), f"Student {number}", f"sid-{number}", None)

    with pytest.raises(RejectedInput) as refusal:
        room.connect(tab_id(150), "Late", "sid-late", None)

    assert refusal.value.code == "too_many_streams"


def test_should_refuse_sixth_connection_when_one_name_has_five_open() -> None:
    room = Room()
    for number in range(5):
        room.connect(tab_id(number), "Avery", f"sid-{number}", None)

    with pytest.raises(RejectedInput) as refusal:
        room.connect(tab_id(5), "Avery", "sid-5", None)

    assert refusal.value.code == "too_many_streams"
    assert room.connect(tab_id(6), "Jordan", "sid-6", None).name == "Jordan"


async def test_should_accept_connection_again_when_an_open_one_ends() -> None:
    room = Room(max_streams=1)
    first = room.connect(TAB_A, "Avery", "sid-a", None)

    room.disconnect(first)

    assert room.connect(TAB_B, "Jordan", "sid-j", None).tab == TAB_B


def test_should_list_one_name_per_present_tab_when_tabs_connect() -> None:
    room = Room()
    room.connect(TAB_A, "Avery", "sid-a", None)
    room.connect(TAB_B, "Avery", "sid-a", None)
    room.connect(TAB_C, "Jordan", "sid-j", None)

    assert sorted(room.names()) == ["Avery", "Avery", "Jordan"]


def test_should_broadcast_presence_to_open_connections_when_new_tab_joins() -> None:
    room = Room()
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)

    joiner = room.connect(TAB_B, "Jordan", "sid-j", None)

    assert sorted(_presence(watcher.queue.get_nowait())) == ["Avery", "Jordan"]
    assert joiner.queue.empty()


def test_should_remove_tab_at_once_and_broadcast_when_tab_leaves() -> None:
    room = Room()
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)
    room.connect(TAB_B, "Jordan", "sid-j", None)
    watcher.queue.get_nowait()

    room.leave(TAB_B)

    assert room.names() == ["Avery"]
    assert _presence(watcher.queue.get_nowait()) == ["Avery"]


async def test_should_change_nothing_when_left_tab_disconnects_later() -> None:
    room = Room(presence_grace=0)
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)
    leaver = room.connect(TAB_B, "Jordan", "sid-j", None)
    room.leave(TAB_B)
    _drain(watcher)

    room.disconnect(leaver)
    room.disconnect(leaver)
    await asyncio.sleep(0.01)

    assert room.names() == ["Avery"]
    assert watcher.queue.empty()


def test_should_do_nothing_when_unknown_tab_leaves() -> None:
    room = Room()
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)

    room.leave(TAB_B)

    assert room.names() == ["Avery"]
    assert watcher.queue.empty()


async def test_should_drop_tab_after_grace_when_its_last_stream_ends() -> None:
    room = Room(presence_grace=0.01)
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)
    ended = room.connect(TAB_B, "Jordan", "sid-j", None)
    watcher.queue.get_nowait()

    room.disconnect(ended)

    assert sorted(room.names()) == ["Avery", "Jordan"]
    update = await asyncio.wait_for(watcher.queue.get(), timeout=1)
    assert _presence(update) == ["Avery"]


async def test_should_keep_tab_listed_without_broadcast_when_it_reconnects_within_grace() -> None:
    room = Room(presence_grace=0)
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)
    ended = room.connect(TAB_B, "Jordan", "sid-j", None)
    watcher.queue.get_nowait()

    room.disconnect(ended)
    room.connect(TAB_B, "Jordan", "sid-j", None)
    await asyncio.sleep(0.01)

    assert sorted(room.names()) == ["Avery", "Jordan"]
    assert watcher.queue.empty()


def test_should_broadcast_new_list_when_tab_reconnects_under_new_name() -> None:
    room = Room()
    watcher = room.connect(TAB_A, "Avery", "sid-a", None)
    room.connect(TAB_B, "Jordan", "sid-j", None)
    watcher.queue.get_nowait()

    room.connect(TAB_B, "Jordan Lee", "sid-j2", None)

    assert sorted(_presence(watcher.queue.get_nowait())) == ["Avery", "Jordan Lee"]
    assert sorted(room.names()) == ["Avery", "Jordan Lee"]


def test_should_mark_connection_overflowed_when_200_events_wait_unread() -> None:
    room = Room()
    slow = room.connect(TAB_A, "Avery", "sid-a", None)
    for number in range(200):
        room.post("Jordan", "sid-j", f"<p>{number}</p>")

    assert not slow.is_overflowed

    room.post("Jordan", "sid-j", "<p>one too many</p>")

    assert slow.is_overflowed
    assert slow.queue.qsize() == 200


def _drain(connection: Connection) -> list[Message | Presence]:
    events: list[Message | Presence] = []
    while not connection.queue.empty():
        events.append(connection.queue.get_nowait())
    return events


def _messages(events: list[Message | Presence]) -> list[Message]:
    return [event for event in events if isinstance(event, Message)]


def _presence(event: Message | Presence) -> list[str]:
    assert isinstance(event, Presence)
    return list(event.names)
