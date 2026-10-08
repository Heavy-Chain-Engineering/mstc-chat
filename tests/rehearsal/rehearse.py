"""Rehearse a class against the deployed chat room and time every delivery (AC-17).

    uv run python tests/rehearsal/rehearse.py --url https://mstc-chat-....run.app

The tool signs in N simulated students named "Rehearsal 01" and up, and keeps one live stream
open for each, reconnecting the way a browser does when the server ends a stream. Every few
seconds a different student posts a numbered probe message. At the end the tool reports the
slowest delivery, every late or missing delivery, every refused or failed request, and how many
times each simulated page saw the server instance change (a restart or a redeploy).

It reads the class password at a hidden prompt and never prints it. It exits 0 when every
student received every probe within 2 seconds and the server refused nothing, 1 when not, and 2
when it cannot sign in. pytest does not collect this file; `make rehearse` runs it.
"""

import argparse
import asyncio
import getpass
import json
import re
import sys
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field

import httpx

DELIVERY_LIMIT_SECONDS = 2.0
# The server's `retry: 1000`: a browser reconnects 1 second after a stream ends.
RECONNECT_DELAY_SECONDS = 1.0
CONNECT_WAIT_SECONDS = 15.0
PROBE = re.compile(r"rehearsal-probe-(\d+)")
LOCAL_HOSTS = {"localhost", "127.0.0.1"}


@dataclass
class Student:
    name: str
    client: httpx.AsyncClient
    tab: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_event_id: str | None = None
    instance: str | None = None
    instance_changes: int = 0
    received: dict[str, float] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


@dataclass
class Probe:
    marker: str
    sent_at: float


def checked_url(value: str) -> str:
    """Accepts https, or plain http to this machine only: sign-in sends the class password."""
    url = urllib.parse.urlsplit(value)
    if url.scheme == "https" and url.hostname:
        return value
    if url.scheme == "http" and url.hostname in LOCAL_HOSTS:
        return value
    raise argparse.ArgumentTypeError(
        f"{value!r} is not an https:// address; plain http is allowed only for localhost "
        "or 127.0.0.1, because sign-in sends the class password"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", required=True, type=checked_url, help="the room's https:// address"
    )
    parser.add_argument("--participants", type=int, default=50)
    parser.add_argument("--duration", type=float, default=60.0, help="seconds of posting")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between probes")
    return parser.parse_args(argv)


def new_client(url: str) -> httpx.AsyncClient:
    # Streams stay quiet between messages; the server ends each one within 20 seconds.
    return httpx.AsyncClient(base_url=url, timeout=httpx.Timeout(10.0, read=30.0))


async def sign_in(student: Student, password: str) -> int:
    try:
        response = await student.client.post(
            "/api/login", json={"name": student.name, "password": password}
        )
    except httpx.HTTPError as error:
        student.problems.append(f"sign-in failed: {type(error).__name__}")
        return 0
    if response.status_code != 200:
        student.problems.append(f"sign-in answered {response.status_code}")
    return response.status_code


def handle_event(student: Student, event: str, data: str, event_id: str | None) -> None:
    now = time.monotonic()
    if event_id is not None:
        student.last_event_id = event_id
    if event == "hello":
        instance = json.loads(data)["instance"]
        if student.instance is not None and instance != student.instance:
            student.instance_changes += 1
        student.instance = instance
    elif event == "message":
        match = PROBE.search(json.loads(data)["html"])
        if match and match.group(0) not in student.received:
            student.received[match.group(0)] = now


async def read_events(student: Student, response: httpx.Response) -> None:
    """Reads Server-Sent Events until the server ends the stream."""
    event, data, event_id = "message", [], None
    async for line in response.aiter_lines():
        if line == "":
            if data:
                handle_event(student, event, "\n".join(data), event_id)
            event, data, event_id = "message", [], None
        elif line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data.append(line.removeprefix("data:").removeprefix(" "))
        elif line.startswith("id:"):
            event_id = line.removeprefix("id:").strip()


async def listen(student: Student) -> None:
    """Keeps one stream open, reconnecting after each end, until the task is cancelled."""
    while True:
        headers = {"Last-Event-ID": student.last_event_id} if student.last_event_id else {}
        try:
            async with student.client.stream(
                "GET", "/api/stream", params={"tab": student.tab}, headers=headers
            ) as response:
                if response.status_code == 200:
                    await read_events(student, response)
                else:
                    student.problems.append(f"stream answered {response.status_code}")
        except httpx.HTTPError as error:
            student.problems.append(f"stream failed: {type(error).__name__}")
        await asyncio.sleep(RECONNECT_DELAY_SECONDS)


async def post_probes(students: list[Student], duration: float, interval: float) -> list[Probe]:
    probes: list[Probe] = []
    started = time.monotonic()
    number = 0
    while time.monotonic() - started < duration:
        author = students[number % len(students)]
        marker = f"rehearsal-probe-{number:04d}"
        sent_at = time.monotonic()
        try:
            response = await author.client.post(
                "/api/messages", json={"text": f"{marker} from {author.name}"}
            )
            if response.status_code == 204:
                probes.append(Probe(marker, sent_at))
            else:
                author.problems.append(f"post answered {response.status_code}")
        except httpx.HTTPError as error:
            author.problems.append(f"post failed: {type(error).__name__}")
        number += 1
        await asyncio.sleep(interval)
    return probes


async def wait_until_connected(students: list[Student]) -> None:
    deadline = time.monotonic() + CONNECT_WAIT_SECONDS
    while time.monotonic() < deadline and any(s.instance is None for s in students):
        await asyncio.sleep(0.2)


async def leave(student: Student) -> None:
    try:
        await student.client.post("/api/leave", content=student.tab)
    except httpx.HTTPError:
        pass  # The room drops the tab 5 seconds after its stream ends anyway.
    await student.client.aclose()


def report(students: list[Student], probes: list[Probe]) -> bool:
    delays = [
        student.received[probe.marker] - probe.sent_at
        for student in students
        for probe in probes
        if probe.marker in student.received
    ]
    expected = len(students) * len(probes)
    late = [delay for delay in delays if delay > DELIVERY_LIMIT_SECONDS]
    missing = expected - len(delays)
    problems = [problem for student in students for problem in student.problems]
    connected = sum(1 for student in students if student.instance is not None)
    changed = [student.instance_changes for student in students if student.instance_changes]

    print(f"Students connected:       {connected} of {len(students)}")
    print(f"Probes posted:            {len(probes)}")
    print(f"Deliveries expected:      {expected}")
    print(f"Slowest delivery:         {max(delays, default=0.0):.3f} s")
    print(f"Late (over {DELIVERY_LIMIT_SECONDS:.0f} s):           {len(late)}")
    print(f"Missing:                  {missing}")
    print(f"Refused or failed:        {len(problems)}")
    for problem in sorted(set(problems)):
        print(f"  {problems.count(problem)} x {problem}")
    print(f"Pages that saw the server instance change: {len(changed)} of {len(students)}")
    if changed:
        print(f"  most changes on one page: {max(changed)}")
    passed = connected == len(students) and bool(probes) and not late and not missing
    passed = passed and not problems
    print("Result:                   " + ("PASS" if passed else "FAIL"))
    return passed


async def rehearse(args: argparse.Namespace, password: str) -> int:
    students = [
        Student(name=f"Rehearsal {number:02d}", client=new_client(args.url))
        for number in range(1, args.participants + 1)
    ]
    first = await sign_in(students[0], password)
    if first != 200:
        print(f"Sign-in as {students[0].name} answered {first or 'nothing'}; check the password.")
        await asyncio.gather(*(leave(student) for student in students))
        return 2
    await asyncio.gather(*(sign_in(student, password) for student in students[1:]))
    listeners = [asyncio.create_task(listen(student)) for student in students]
    await wait_until_connected(students)
    probes = await post_probes(students, args.duration, args.interval)
    await asyncio.sleep(DELIVERY_LIMIT_SECONDS + 1.0)
    for listener in listeners:
        listener.cancel()
    await asyncio.gather(*listeners, return_exceptions=True)
    await asyncio.gather(*(leave(student) for student in students))
    return 0 if report(students, probes) else 1


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    password = getpass.getpass("Class password (typing stays hidden): ")
    print(f"Rehearsing {args.participants} students against {args.url} for {args.duration:.0f} s")
    return asyncio.run(rehearse(args, password))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
