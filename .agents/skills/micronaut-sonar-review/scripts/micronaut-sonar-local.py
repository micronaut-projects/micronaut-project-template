#!/usr/bin/env python3
from __future__ import annotations

import base64
import http.client
import json
import os
import pathlib
import random
import re
import shlex
import shutil
import string
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def log(message: str) -> None:
    print(f"[sonar-local] {message}", flush=True)


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        die(f"Required command not found: {command}", 2)


def env_bool(name: str) -> bool:
    return name in os.environ and os.environ[name] != ""


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "project"


def default_run_id() -> str:
    return f"{time.strftime('%Y%m%d%H%M%S')}-{os.getpid()}-{random.randint(1000, 9999)}"


def split_env_args(name: str, default: str = "") -> list[str]:
    value = os.environ[name] if name in os.environ else default
    if not value:
        return []
    try:
        return shlex.split(value)
    except ValueError as exc:
        die(f"{name} could not be parsed as shell-style arguments: {exc}", 2)


SONAR_IMAGE = os.environ.get("SONAR_IMAGE", "sonarqube:community")
SONAR_GRADLE_TASK = os.environ.get("SONAR_GRADLE_TASK", "auto")
SONAR_GRADLE_ARGS = split_env_args("SONAR_GRADLE_ARGS", "--no-parallel --continue")
SONAR_SCANNER_ARGS = split_env_args("SONAR_SCANNER_ARGS")
SONAR_SKIP_GRADLE = os.environ.get("SONAR_SKIP_GRADLE", "false") == "true"
SONAR_PROJECT_KEY = os.environ.get("SONAR_PROJECT_KEY", pathlib.Path.cwd().name)
SONAR_START_TIMEOUT_SECONDS = int(os.environ.get("SONAR_START_TIMEOUT_SECONDS", "240"))
SONAR_QUALITY_GATE_TIMEOUT_SECONDS = os.environ.get("SONAR_QUALITY_GATE_TIMEOUT_SECONDS", "180")
SONAR_PORT_WAS_SET = env_bool("SONAR_PORT")
SONAR_URL_WAS_SET = env_bool("SONAR_URL")
SONAR_RUN_ID = os.environ.get("SONAR_RUN_ID", default_run_id())
PROJECT_SLUG = slugify(pathlib.Path.cwd().name)
SONAR_CONTAINER = os.environ.get("SONAR_CONTAINER", f"codex-sonarqube-{PROJECT_SLUG}-{SONAR_RUN_ID}")
SONAR_OUTPUT_DIR = pathlib.Path(
    os.environ.get("SONAR_OUTPUT_DIR", f"build/sonar-local/{SONAR_RUN_ID}")
).resolve()
SONAR_STATE_DIR = pathlib.Path(os.environ.get("SONAR_STATE_DIR", str(SONAR_OUTPUT_DIR / "state"))).resolve()
SONAR_USER_HOME = pathlib.Path(os.environ.get("SONAR_USER_HOME", str(SONAR_OUTPUT_DIR / "sonar-user-home"))).resolve()
SONAR_BIND_HOST = os.environ.get("SONAR_BIND_HOST", "127.0.0.1")
SONAR_URL_HOST = os.environ.get("SONAR_URL_HOST", "127.0.0.1")
SONAR_PORT = os.environ.get("SONAR_PORT", "")

if SONAR_URL_WAS_SET:
    SONAR_URL = os.environ["SONAR_URL"]
elif SONAR_PORT_WAS_SET:
    SONAR_URL = f"http://{SONAR_URL_HOST}:{SONAR_PORT}"
else:
    SONAR_URL = ""

SONAR_TOKEN = os.environ.get("SONAR_TOKEN", "")
SONAR_TOKEN_FILE = os.environ.get("SONAR_TOKEN_FILE", "")

SONAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SONAR_STATE_DIR.mkdir(parents=True, exist_ok=True)
SONAR_USER_HOME.mkdir(parents=True, exist_ok=True)


def basic_auth_header(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request(
    path: str,
    *,
    params: dict[str, str] | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str = "",
    method: str = "GET",
    timeout: int = 60,
) -> bytes:
    url = f"{SONAR_URL}{path}"
    data = None
    if params:
        encoded = urllib.parse.urlencode(params)
        if method == "GET":
            url = f"{url}?{encoded}"
        else:
            data = encoded.encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", basic_auth_header(token, ""))
    elif username is not None:
        req.add_header("Authorization", basic_auth_header(username, password))
    if method != "GET":
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def request_json(
    path: str,
    *,
    params: dict[str, str] | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str = "",
    method: str = "GET",
    timeout: int = 60,
) -> dict:
    body = request(
        path,
        params=params,
        token=token,
        username=username,
        password=password,
        method=method,
        timeout=timeout,
    ).decode("utf-8")
    return json.loads(body) if body else {}


def run_command(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=capture,
        text=True,
    )


def docker_names(all_containers: bool = False) -> set[str]:
    command = ["docker", "ps", "--format", "{{.Names}}"]
    if all_containers:
        command.insert(2, "-a")
    result = run_command(command, capture=True)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def ensure_sonar_url() -> None:
    if not SONAR_URL:
        die("SONAR_URL is not set. Let this helper start a local container, or set SONAR_URL explicitly.", 4)


def resolve_container_url() -> None:
    global SONAR_PORT, SONAR_URL
    if SONAR_URL_WAS_SET:
        return

    result = run_command(["docker", "port", SONAR_CONTAINER, "9000/tcp"], capture=True)
    first_line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
    if not first_line:
        die(f"Could not resolve published SonarQube port for container {SONAR_CONTAINER}", 3)
    resolved_port = first_line.rsplit(":", 1)[-1]
    if not resolved_port or resolved_port == first_line:
        die(f"Could not parse published SonarQube port from: {first_line}", 3)
    SONAR_PORT = resolved_port
    SONAR_URL = f"http://{SONAR_URL_HOST}:{SONAR_PORT}"
    os.environ["SONAR_PORT"] = SONAR_PORT
    os.environ["SONAR_URL"] = SONAR_URL
    log(f"Resolved SonarQube URL: {SONAR_URL}")


def quote_env(value: str) -> str:
    return shlex.quote(value)


def write_run_env() -> None:
    lines = {
        "SONAR_RUN_ID": SONAR_RUN_ID,
        "SONAR_URL": SONAR_URL,
        "SONAR_PROJECT_KEY": SONAR_PROJECT_KEY,
        "SONAR_OUTPUT_DIR": str(SONAR_OUTPUT_DIR),
        "SONAR_CONTAINER": SONAR_CONTAINER,
        "SONAR_IMAGE": SONAR_IMAGE,
        "SONAR_GRADLE_TASK": SONAR_GRADLE_TASK,
        "SONAR_SKIP_GRADLE": "true" if SONAR_SKIP_GRADLE else "false",
        "SONAR_PORT": SONAR_PORT,
        "SONAR_STATE_DIR": str(SONAR_STATE_DIR),
        "SONAR_USER_HOME": str(SONAR_USER_HOME),
    }
    if SONAR_GRADLE_ARGS:
        lines["SONAR_GRADLE_ARGS"] = " ".join(shlex.quote(arg) for arg in SONAR_GRADLE_ARGS)
    if SONAR_SCANNER_ARGS:
        lines["SONAR_SCANNER_ARGS"] = " ".join(shlex.quote(arg) for arg in SONAR_SCANNER_ARGS)
    if SONAR_TOKEN_FILE:
        lines["SONAR_TOKEN_FILE"] = SONAR_TOKEN_FILE

    (SONAR_OUTPUT_DIR / "run.env").write_text(
        "".join(f"{key}={quote_env(value)}\n" for key, value in lines.items()),
        encoding="utf-8",
    )


def wait_for_sonar() -> None:
    ensure_sonar_url()
    deadline = time.monotonic() + SONAR_START_TIMEOUT_SECONDS
    status_payload: dict | None = None
    while time.monotonic() < deadline:
        try:
            status_payload = request_json("/api/system/status", timeout=10)
            (SONAR_OUTPUT_DIR / "system-status.json").write_text(
                json.dumps(status_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if status_payload.get("status") == "UP":
                return
        except (
            http.client.RemoteDisconnected,
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ):
            status_payload = None
        time.sleep(5)

    last_status = status_payload.get("status", "") if status_payload else ""
    if last_status:
        die(f"Timed out waiting for SonarQube status UP; last status was {last_status}", 3)
    die(f"Timed out waiting for SonarQube at {SONAR_URL}", 3)


def ensure_local_sonar() -> None:
    if SONAR_URL_WAS_SET:
        log(f"Using configured SonarQube at {SONAR_URL}")
        wait_for_sonar()
        return

    if SONAR_TOKEN and SONAR_URL:
        log(f"Using configured SonarQube at {SONAR_URL}")
        wait_for_sonar()
        return

    if SONAR_TOKEN:
        die("SONAR_TOKEN was provided but no SONAR_URL or SONAR_PORT was configured.", 4)

    require_command("docker")
    run_command(["docker", "info"], capture=True)

    running = docker_names()
    all_names = docker_names(all_containers=True)
    if SONAR_CONTAINER in running:
        log(f"Reusing running container {SONAR_CONTAINER}")
    elif SONAR_CONTAINER in all_names:
        log(f"Starting existing container {SONAR_CONTAINER}")
        run_command(["docker", "start", SONAR_CONTAINER], capture=True)
    else:
        publish_arg = (
            f"{SONAR_BIND_HOST}:{SONAR_PORT}:9000"
            if SONAR_PORT_WAS_SET
            else f"{SONAR_BIND_HOST}::9000"
        )
        log(f"Starting {SONAR_IMAGE} as {SONAR_CONTAINER}")
        run_command(["docker", "run", "-d", "--name", SONAR_CONTAINER, "-p", publish_arg, SONAR_IMAGE], capture=True)

    resolve_container_url()
    wait_for_sonar()


def sanitize_state_key(value: str) -> str:
    return "".join(ch if ch in string.ascii_letters + string.digits + "_.-" else "_" for ch in value)


def token_is_valid(token: str) -> bool:
    try:
        response = request_json("/api/authentication/validate", token=token)
    except (
        http.client.RemoteDisconnected,
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return False
    return response.get("valid") is True


def generate_token(password: str, token_file: pathlib.Path) -> bool:
    global SONAR_TOKEN, SONAR_TOKEN_FILE
    try:
        response = request_json(
            "/api/user_tokens/generate",
            params={"name": f"codex-local-{int(time.time())}"},
            username="admin",
            password=password,
            method="POST",
        )
    except (
        http.client.RemoteDisconnected,
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return False
    token = response.get("token")
    if not token:
        return False
    token_file.write_text(token + "\n", encoding="utf-8")
    SONAR_TOKEN = token
    SONAR_TOKEN_FILE = str(token_file)
    os.environ["SONAR_TOKEN"] = token
    os.environ["SONAR_TOKEN_FILE"] = SONAR_TOKEN_FILE
    return True


def change_default_password(new_password: str) -> bool:
    try:
        request(
            "/api/users/change_password",
            params={"login": "admin", "previousPassword": "admin", "password": new_password},
            username="admin",
            password="admin",
            method="POST",
        )
    except (http.client.RemoteDisconnected, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False
    return True


def ensure_local_token() -> None:
    global SONAR_TOKEN, SONAR_TOKEN_FILE
    if SONAR_TOKEN:
        return

    state_key = sanitize_state_key(f"{SONAR_CONTAINER}-{SONAR_PORT or SONAR_URL}")
    password_file = SONAR_STATE_DIR / f"{state_key}-admin-password.txt"
    token_file = SONAR_STATE_DIR / f"{state_key}-token.txt"

    if token_file.is_file():
        token = token_file.read_text(encoding="utf-8").strip()
        if token and token_is_valid(token):
            SONAR_TOKEN = token
            SONAR_TOKEN_FILE = str(token_file)
            os.environ["SONAR_TOKEN"] = SONAR_TOKEN
            os.environ["SONAR_TOKEN_FILE"] = SONAR_TOKEN_FILE
            return
        token_file.unlink(missing_ok=True)

    if password_file.is_file():
        saved_password = password_file.read_text(encoding="utf-8").strip()
        if saved_password and generate_token(saved_password, token_file):
            return

    new_password = f"codex-{int(time.time())}-{random.randint(1000, 99999)}"
    if change_default_password(new_password):
        password_file.write_text(new_password + "\n", encoding="utf-8")
        if generate_token(new_password, token_file):
            return

    # Some newer local images still validate admin/admin but reject the password
    # change path during bootstrap. In that case generate a local token directly.
    if generate_token("admin", token_file):
        return

    die(
        "Could not authenticate with local SonarQube using saved/default local admin credentials.\n"
        f"Set SONAR_TOKEN for {SONAR_URL} or remove/recreate the {SONAR_CONTAINER} container.",
        4,
    )


def run_gradle_sonar() -> int:
    if not pathlib.Path("./gradlew").is_file():
        die("Run this script from a Micronaut repository root containing ./gradlew", 5)

    log(f"Running ./gradlew {SONAR_GRADLE_TASK} for {SONAR_PROJECT_KEY}")
    try:
        gradle_task_args = shlex.split(SONAR_GRADLE_TASK)
    except ValueError as exc:
        die(f"SONAR_GRADLE_TASK could not be parsed as shell-style arguments: {exc}", 2)
    if not gradle_task_args:
        die("SONAR_GRADLE_TASK resolved to an empty command.", 2)

    command = [
        "./gradlew",
        *gradle_task_args,
        *SONAR_GRADLE_ARGS,
        f"-Dsonar.host.url={SONAR_URL}",
        f"-Dsonar.token={SONAR_TOKEN}",
        f"-Dsonar.projectKey={SONAR_PROJECT_KEY}",
        f"-Dsonar.userHome={SONAR_USER_HOME}",
        "-Dsonar.qualitygate.wait=true",
        f"-Dsonar.qualitygate.timeout={SONAR_QUALITY_GATE_TIMEOUT_SECONDS}",
        *SONAR_SCANNER_ARGS,
    ]
    log_file = SONAR_OUTPUT_DIR / "gradle-sonar.log"
    with log_file.open("w", encoding="utf-8") as handle:
        env = os.environ.copy()
        env["SONAR_USER_HOME"] = str(SONAR_USER_HOME)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            handle.write(line)
        return process.wait()


def resolve_gradle_task() -> None:
    global SONAR_GRADLE_TASK
    if SONAR_GRADLE_TASK != "auto":
        return

    tasks_file = SONAR_OUTPUT_DIR / "gradle-tasks.txt"
    command = ["./gradlew", "-q", "-Dorg.gradle.vfs.watch=false", "tasks", "--all"]
    with tasks_file.open("w", encoding="utf-8") as handle:
        process = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, text=True)
    if process.returncode != 0:
        die(f"Gradle task discovery failed; output was written to {tasks_file}", process.returncode)

    content = tasks_file.read_text(encoding="utf-8", errors="replace")
    if re.search(r"^sonar([ \t]|-)", content, re.MULTILINE):
        SONAR_GRADLE_TASK = "sonar"
    elif re.search(r"^sonarqube([ \t]|-)", content, re.MULTILINE):
        SONAR_GRADLE_TASK = "sonarqube"
    else:
        die(
            "Could not find a root Gradle sonar or sonarqube task.\n"
            "Set SONAR_GRADLE_TASK explicitly if this repository uses a custom task.\n"
            f"Task list was written to {tasks_file}",
            6,
        )


def extract_results() -> int:
    log("Extracting SonarQube results")
    env = os.environ.copy()
    env.update(
        {
            "SONAR_TOKEN": SONAR_TOKEN,
            "SONAR_URL": SONAR_URL,
            "SONAR_PROJECT_KEY": SONAR_PROJECT_KEY,
            "SONAR_OUTPUT_DIR": str(SONAR_OUTPUT_DIR),
        }
    )
    if SONAR_TOKEN_FILE:
        env["SONAR_TOKEN_FILE"] = SONAR_TOKEN_FILE
    process = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "micronaut-sonar-extract-issues.py")],
        env=env,
        text=True,
    )
    return process.returncode


def main() -> None:
    if not pathlib.Path("./gradlew").is_file():
        die("Run this script from a Micronaut repository root containing ./gradlew", 5)

    ensure_local_sonar()
    write_run_env()
    ensure_local_token()
    write_run_env()
    log(f"Output directory: {SONAR_OUTPUT_DIR}")

    if SONAR_SKIP_GRADLE:
        log("Skipping Gradle analysis because SONAR_SKIP_GRADLE=true")
        return

    resolve_gradle_task()
    write_run_env()
    gradle_status = run_gradle_sonar()
    extract_status = extract_results()
    if gradle_status != 0:
        die(f"Gradle Sonar task failed with exit code {gradle_status}; extracted results may be partial.", gradle_status)
    if extract_status != 0:
        die(f"Sonar result extraction failed with exit code {extract_status}.", extract_status)


if __name__ == "__main__":
    main()
