"""The container, deploy and CI files keep secrets hidden and set every Cloud Run rule.

The Makefile tests run its targets in a throwaway git repository with a fake `gcloud` first on
PATH. The fake records each call's arguments and anything piped to it, so the tests see exactly
what each target would send to Google Cloud, without an account or a network.
"""

import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "mstc-chat"
RUNTIME_ACCOUNT = "mstc-chat-run@mstc-chat.iam.gserviceaccount.com"
BUILD_ACCOUNT = "mstc-chat-build@mstc-chat.iam.gserviceaccount.com"
SERVICE_URL = "https://mstc-chat-test-uc.a.run.app"
SECRET_SHAPED = re.compile(r"secret|password|passwd|token|key|credential", re.IGNORECASE)
COMMIT_SHA = re.compile(r"@[0-9a-f]{40}(\s|$)")

# The fake gcloud: logs its arguments, keeps what is piped to it, answers the two lookups the
# Makefile makes, and fails every `describe` when FAKE_GCLOUD_MISSING is set.
FAKE_GCLOUD = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_GCLOUD_LOG"
case "$*" in *--data-file=-*) cat >> "$FAKE_GCLOUD_STDIN" ;; esac
case "$*" in *" describe "*) [ -n "${FAKE_GCLOUD_MISSING:-}" ] && exit 1 ;; esac
case "$*" in
  "secrets versions list"*) printf '%s' "${FAKE_VERSION_NUMBER}" ;;
  "run services describe"*"status.url"*) printf '%s\n' "$FAKE_SERVICE_URL" ;;
esac
exit 0
"""


@dataclass
class MakeRun:
    returncode: int
    output: str
    calls: list[str]
    piped: str


def run_make(repo: Path, target: str, stdin: str = "", **fake_env: str) -> MakeRun:
    log = repo.parent / "gcloud.log"
    piped = repo.parent / "gcloud.stdin"
    log.write_text("")
    piped.write_text("")
    env = {
        **os.environ,
        "PATH": f"{repo.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "FAKE_GCLOUD_LOG": str(log),
        "FAKE_GCLOUD_STDIN": str(piped),
        "FAKE_VERSION_NUMBER": "7",
        "FAKE_SERVICE_URL": SERVICE_URL,
        **fake_env,
    }
    make = shutil.which("make") or "make"
    result = subprocess.run(  # noqa: S603  # fixed arguments; the target is a test constant
        [make, "--no-print-directory", target],
        cwd=repo,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return MakeRun(
        returncode=result.returncode,
        output=result.stdout + result.stderr,
        calls=log.read_text().splitlines(),
        piped=piped.read_text(),
    )


def git(repo: Path, *args: str) -> str:
    git_exe = shutil.which("git") or "git"
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    hooks_off = ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"]
    return subprocess.run(  # noqa: S603  # fixed arguments from the tests
        [git_exe, *identity, *hooks_off, *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository holding only the project's Makefile, with one uncommitted file."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gcloud"
    fake.write_text(FAKE_GCLOUD)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    work = tmp_path / "repo"
    work.mkdir()
    shutil.copy(ROOT / "Makefile", work / "Makefile")
    git(work, "init", "-q")
    git(work, "add", "Makefile")
    git(work, "commit", "-q", "-m", "test: makefile")
    (work / "notes.txt").write_text("not committed\n")
    return work


def calls_with(run: MakeRun, *words: str) -> list[str]:
    return [call for call in run.calls if all(word in call for word in words)]


def deploy_call(run: MakeRun) -> str:
    deploys = calls_with(run, "run deploy")
    assert len(deploys) == 1, run.output
    return deploys[0]


def ignore_patterns(name: str) -> set[str]:
    lines = (ROOT / name).read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def dockerfile() -> str:
    """The Dockerfile with each continued line joined, so an instruction reads as one line."""
    return (ROOT / "Dockerfile").read_text().replace("\\\n", " ")


def dockerfile_instructions(keyword: str) -> list[str]:
    pattern = re.compile(rf"^{keyword}\s+(.+)$", re.MULTILINE | re.IGNORECASE)
    return pattern.findall(dockerfile())


def final_stage() -> str:
    return re.split(r"^FROM\s", dockerfile(), flags=re.MULTILINE | re.IGNORECASE)[-1]


def workflow() -> str:
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text()


# --- What the image build and the source upload leave out (AC-23) ---


def test_dockerignore_excludes_env_files() -> None:
    assert {".env", ".env.*"} <= ignore_patterns(".dockerignore")


def test_dockerignore_excludes_git_history() -> None:
    assert ".git" in ignore_patterns(".dockerignore")


def test_gcloudignore_excludes_env_files() -> None:
    assert {".env", ".env.*"} <= ignore_patterns(".gcloudignore")


def test_gcloudignore_excludes_git_history() -> None:
    assert ".git" in ignore_patterns(".gcloudignore")


@pytest.mark.parametrize("path", [".env", ".env.local"])
def test_git_ignores_env_files(path: str) -> None:
    git_exe = shutil.which("git") or "git"
    ignored = subprocess.run(  # noqa: S603  # fixed arguments
        [git_exe, "check-ignore", "-q", "--no-index", path], cwd=ROOT, check=False
    )
    assert ignored.returncode == 0


# --- The image (AC-23, AC-26, ADR-07) ---


def test_dockerfile_declares_no_secret_in_arg_or_env() -> None:
    declared = dockerfile_instructions("ARG") + dockerfile_instructions("ENV")
    assert [line for line in declared if SECRET_SHAPED.search(line)] == []


def test_dockerfile_copies_no_env_file() -> None:
    assert [line for line in dockerfile_instructions("COPY") if ".env" in line] == []


def test_dockerfile_runtime_stage_runs_as_non_root_user() -> None:
    users = re.findall(r"^USER\s+(\S+)", final_stage(), flags=re.MULTILINE)
    assert users, "the runtime stage sets no USER, so Cloud Run runs it as root"
    assert users[-1].split(":")[0] not in {"root", "0"}


def test_dockerfile_turns_build_check_findings_into_errors() -> None:
    assert dockerfile().splitlines()[0] == "# check=error=true"


def test_dockerfile_installs_client_packages_without_install_scripts() -> None:
    assert "npm ci --ignore-scripts" in dockerfile()


def test_dockerfile_pins_every_base_image_to_an_exact_version() -> None:
    stage_names = set(re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", dockerfile(), re.M | re.I))
    images = [ref for ref in dockerfile_instructions("FROM") if ref.split()[0] not in stage_names]
    unpinned = [ref for ref in images if not re.search(r":\d+\.\d+\.\d+", ref.split()[0])]
    assert images
    assert unpinned == []


# --- The deploy command (AC-16, AC-20) ---


def test_deploy_pins_both_secrets_to_looked_up_version_numbers(repo: Path) -> None:
    run = run_make(repo, "deploy", FAKE_VERSION_NUMBER="7")

    flags = deploy_call(run).split()
    assert run.returncode == 0, run.output
    assert "--set-secrets=CLASS_PASSWORD=class-password:7,SESSION_SECRET=session-secret:7" in flags


@pytest.mark.parametrize(
    "flag",
    [
        "--project=mstc-chat",
        "--region=us-central1",
        "--source=.",
        "--max=1",
        f"--service-account={RUNTIME_ACCOUNT}",
        f"--build-service-account=projects/{PROJECT}/serviceAccounts/{BUILD_ACCOUNT}",
        "--concurrency=250",
        "--timeout=60",
        "--cpu=1",
        "--memory=512Mi",
        "--no-cpu-boost",
        "--allow-unauthenticated",
    ],
)
def test_deploy_sets_cloud_run_setting(repo: Path, flag: str) -> None:
    run = run_make(repo, "deploy")

    assert flag in deploy_call(run).split()


def test_deploy_passes_no_secret_as_a_plain_environment_variable(repo: Path) -> None:
    call = deploy_call(run_make(repo, "deploy"))

    assert "env-vars" not in call
    assert "latest" not in call


def test_deploy_prints_address_commit_and_uncommitted_changes(repo: Path) -> None:
    run = run_make(repo, "deploy")

    assert run.returncode == 0, run.output
    assert SERVICE_URL in run.output
    assert git(repo, "rev-parse", "--short", "HEAD") in run.output
    assert "?? notes.txt" in run.output


def test_deploy_stops_before_deploying_when_a_secret_has_no_enabled_version(repo: Path) -> None:
    run = run_make(repo, "deploy", FAKE_VERSION_NUMBER="")

    assert run.returncode != 0
    assert calls_with(run, "run deploy") == []
    assert "class-password" in run.output


# --- Lecture day (AC-18) ---


@pytest.mark.parametrize(("target", "minimum"), [("warm-up", "1"), ("cool-down", "0")])
def test_warm_up_and_cool_down_change_only_the_service_minimum(
    repo: Path, target: str, minimum: str
) -> None:
    run = run_make(repo, target)

    updates = calls_with(run, "run services update")
    assert run.returncode == 0, run.output
    assert len(updates) == 1
    assert f"--min={minimum}" in updates[0].split()
    assert "--min-instances" not in updates[0]
    assert calls_with(run, "run deploy") == []


# --- Secrets enter without a trace (AC-22) ---


def test_class_password_goes_to_secret_manager_through_standard_input(repo: Path) -> None:
    password = "correct horse battery staple"  # noqa: S105  # a throwaway test value

    run = run_make(repo, "class-password", stdin=f"{password}\n")

    assert run.returncode == 0, run.output
    assert calls_with(run, "secrets versions add class-password", "--data-file=-")
    assert run.piped == password
    assert password not in "\n".join(run.calls)
    assert password not in run.output


def test_class_password_refuses_an_empty_entry(repo: Path) -> None:
    run = run_make(repo, "class-password", stdin="\n")

    assert run.returncode != 0
    assert calls_with(run, "secrets versions add") == []


def test_session_secret_is_generated_and_never_shown(repo: Path) -> None:
    run = run_make(repo, "session-secret")

    assert run.returncode == 0, run.output
    assert calls_with(run, "secrets versions add session-secret", "--data-file=-")
    assert len(run.piped) >= 32
    assert "\n" not in run.piped
    assert run.piped not in "\n".join(run.calls)
    assert run.piped not in run.output


# --- One-time setup: idempotent, least privilege (AC-20) ---


def test_setup_creates_nothing_when_everything_exists(repo: Path) -> None:
    run = run_make(repo, "setup")

    assert run.returncode == 0, run.output
    assert calls_with(run, " create ") == []
    assert calls_with(run, "versions add") == []


def test_setup_creates_missing_accounts_secrets_and_repository(repo: Path) -> None:
    run = run_make(repo, "setup", FAKE_GCLOUD_MISSING="1", FAKE_VERSION_NUMBER="")

    assert run.returncode == 0, run.output
    assert calls_with(run, "iam service-accounts create mstc-chat-run ")
    assert calls_with(run, "iam service-accounts create mstc-chat-build ")
    assert calls_with(run, "secrets create class-password ")
    assert calls_with(run, "secrets create session-secret ")
    assert calls_with(run, "artifacts repositories create cloud-run-source-deploy ")
    assert calls_with(run, "secrets versions add class-password") == []


def test_setup_lets_the_runtime_account_read_the_two_secrets_and_nothing_else(repo: Path) -> None:
    run = run_make(repo, "setup")

    grants = calls_with(run, "add-iam-policy-binding", RUNTIME_ACCOUNT)
    assert sorted(call.split()[0:3] for call in grants) == [
        ["secrets", "add-iam-policy-binding", "class-password"],
        ["secrets", "add-iam-policy-binding", "session-secret"],
    ]
    assert calls_with(run, RUNTIME_ACCOUNT, "roles/secretmanager.secretAccessor") == grants


def test_setup_gives_the_build_account_only_the_cloud_run_builder_role(repo: Path) -> None:
    run = run_make(repo, "setup")

    grants = calls_with(run, "add-iam-policy-binding", BUILD_ACCOUNT)
    assert len(grants) == 1
    assert "--role=roles/run.builder" in grants[0].split()
    assert calls_with(run, "roles/editor") == []
    assert calls_with(run, "roles/owner") == []


# --- CI (AC-24, AC-26) ---


def test_ci_workflow_is_read_only() -> None:
    assert re.search(r"^permissions:\n  contents: read\n", workflow(), re.MULTILINE)
    assert ": write" not in workflow()


def test_ci_workflow_uses_no_secrets() -> None:
    assert "secrets." not in workflow()


def test_ci_workflow_never_runs_on_pull_request_target() -> None:
    assert "pull_request_target" not in workflow()


def test_ci_pins_every_action_to_a_commit_sha() -> None:
    uses = re.findall(r"uses:\s*(\S+.*)$", workflow(), flags=re.MULTILINE)
    assert uses
    assert [ref for ref in uses if not COMMIT_SHA.search(ref)] == []


def test_ci_installs_npm_packages_without_install_scripts() -> None:
    installs = re.findall(r"npm .*\bci\b.*$", workflow(), flags=re.MULTILINE)
    assert installs
    assert [line for line in installs if "--ignore-scripts" not in line] == []
