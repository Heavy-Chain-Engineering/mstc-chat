from backend.room import Room

TAB_A = "00000000-0000-4000-8000-00000000000a"


def test_should_replay_only_newest_200_oldest_first_when_late_joiner_connects() -> None:
    room = Room()
    for number in range(1, 206):
        room.post("Avery", "sid-avery", f"<p>post {number}</p>")

    connection = room.connect(TAB_A, "Jordan", "sid-jordan", None)

    assert [message.seq for message in connection.replay] == list(range(6, 206))
    assert connection.replay[0].html == "<p>post 6</p>"
    assert connection.replay[-1].html == "<p>post 205</p>"
