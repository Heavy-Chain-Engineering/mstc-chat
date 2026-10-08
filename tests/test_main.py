from pathlib import Path

import pytest
from starlette.applications import Starlette

from backend.__main__ import Settings, main, read_settings
from tests.conftest import CLASS_PASSWORD, SESSION_SECRET

GOOD_ENVIRONMENT = {"CLASS_PASSWORD": CLASS_PASSWORD, "SESSION_SECRET": SESSION_SECRET}


class RecordingServer:
    """Stands in for uvicorn.run, the external server, and records how it was started."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    def __call__(
        self,
        app: Starlette,
        *,
        host: str,
        port: int,
        access_log: bool,
        timeout_graceful_shutdown: int,
    ) -> None:
        self.calls.append(
            (
                app,
                {
                    "host": host,
                    "port": port,
                    "access_log": access_log,
                    "timeout_graceful_shutdown": timeout_graceful_shutdown,
                },
            )
        )


def test_should_read_both_secrets_and_default_port_when_environment_is_complete() -> None:
    assert read_settings(GOOD_ENVIRONMENT) == Settings(CLASS_PASSWORD, SESSION_SECRET, 8080)


def test_should_read_port_when_environment_sets_it() -> None:
    assert read_settings(GOOD_ENVIRONMENT | {"PORT": "9000"}).port == 9000


@pytest.mark.parametrize(
    ("environment", "setting"),
    [
        ({"SESSION_SECRET": SESSION_SECRET}, "CLASS_PASSWORD"),
        ({"CLASS_PASSWORD": "", "SESSION_SECRET": SESSION_SECRET}, "CLASS_PASSWORD"),
        ({"CLASS_PASSWORD": CLASS_PASSWORD}, "SESSION_SECRET"),
        ({"CLASS_PASSWORD": CLASS_PASSWORD, "SESSION_SECRET": "s" * 31}, "SESSION_SECRET"),
        (GOOD_ENVIRONMENT | {"PORT": "eighty"}, "PORT"),
    ],
)
def test_should_refuse_naming_setting_never_value_when_setting_is_missing_or_bad_ac21(
    environment: dict[str, str], setting: str
) -> None:
    with pytest.raises(ValueError, match=setting) as refusal:
        read_settings(environment)

    assert CLASS_PASSWORD not in str(refusal.value)
    assert "s" * 31 not in str(refusal.value)
    assert "eighty" not in str(refusal.value)


def test_should_accept_session_secret_when_it_has_exactly_32_characters() -> None:
    environment = {"CLASS_PASSWORD": CLASS_PASSWORD, "SESSION_SECRET": "s" * 32}

    assert read_settings(environment).session_secret == "s" * 32


def test_should_exit_1_naming_setting_never_value_when_secret_is_short_ac21(
    static_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server = RecordingServer()
    environment = {"CLASS_PASSWORD": CLASS_PASSWORD, "SESSION_SECRET": "short-secret-value"}

    code = main(environment, run=server, static_dir=static_dir)

    output = capsys.readouterr()
    assert code == 1
    assert server.calls == []
    assert "SESSION_SECRET" in output.err
    assert "short-secret-value" not in output.err + output.out
    assert CLASS_PASSWORD not in output.err + output.out


def test_should_exit_1_when_built_client_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server = RecordingServer()

    code = main(GOOD_ENVIRONMENT, run=server, static_dir=tmp_path)

    assert code == 1
    assert server.calls == []
    assert "index.html" in capsys.readouterr().err


def test_should_run_one_app_object_on_all_interfaces_without_access_log_when_settings_hold(
    static_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server = RecordingServer()

    code = main(GOOD_ENVIRONMENT | {"PORT": "9123"}, run=server, static_dir=static_dir)

    output = capsys.readouterr()
    assert code == 0
    assert len(server.calls) == 1
    app, options = server.calls[0]
    assert isinstance(app, Starlette)
    assert options == {
        "host": "0.0.0.0",
        "port": 9123,
        "access_log": False,
        "timeout_graceful_shutdown": 5,
    }
    assert "9123" in output.out
    assert SESSION_SECRET not in output.out + output.err
    assert CLASS_PASSWORD not in output.out + output.err
