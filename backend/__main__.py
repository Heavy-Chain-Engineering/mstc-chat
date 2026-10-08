"""Starts the chat server: `python -m backend` (ADR-01).

It reads both secrets from the environment and refuses to start, naming the setting but never
its value, when one is missing or the session secret is too short (AC-21).
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple, Protocol

import uvicorn

from backend.app import ChatApp, create_app

DEFAULT_PORT = 8080
MIN_SESSION_SECRET_LENGTH = 32
GRACEFUL_SHUTDOWN_SECONDS = 5
CLIENT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class Settings(NamedTuple):
    class_password: str
    session_secret: str
    port: int


class ServerRunner(Protocol):
    def __call__(
        self,
        app: ChatApp,
        *,
        host: str,
        port: int,
        access_log: bool,
        timeout_graceful_shutdown: int,
    ) -> None: ...


def read_settings(environ: Mapping[str, str]) -> Settings:
    """Raises ValueError whose message names the bad setting and never holds its value."""
    class_password = environ.get("CLASS_PASSWORD", "")
    if not class_password:
        raise ValueError("CLASS_PASSWORD is not set.")
    session_secret = environ.get("SESSION_SECRET", "")
    if not session_secret:
        raise ValueError("SESSION_SECRET is not set.")
    if len(session_secret) < MIN_SESSION_SECRET_LENGTH:
        raise ValueError(
            f"SESSION_SECRET must be at least {MIN_SESSION_SECRET_LENGTH} characters long."
        )
    port_text = environ.get("PORT", str(DEFAULT_PORT))
    if not port_text.isdigit():
        raise ValueError("PORT must be a whole number.")
    return Settings(class_password, session_secret, int(port_text))


def main(
    environ: Mapping[str, str] | None = None,
    *,
    run: ServerRunner = uvicorn.run,
    static_dir: Path = CLIENT_DIR,
) -> int:
    try:
        settings = read_settings(os.environ if environ is None else environ)
    except ValueError as refusal:
        print(f"MSTC Chat cannot start: {refusal}", file=sys.stderr)
        return 1
    if not (static_dir / "index.html").is_file():
        print(
            f"MSTC Chat cannot start: {static_dir / 'index.html'} is missing; build the client.",
            file=sys.stderr,
        )
        return 1
    app = create_app(
        class_password=settings.class_password,
        session_secret=settings.session_secret,
        static_dir=static_dir,
    )
    print(f"MSTC Chat listening on port {settings.port}, instance {app.state.room.instance}")
    # The app object, not an import string, keeps uvicorn to one process and one room.
    run(
        app,
        host="0.0.0.0",  # noqa: S104 - Cloud Run's container contract needs every interface.
        port=settings.port,
        access_log=False,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
