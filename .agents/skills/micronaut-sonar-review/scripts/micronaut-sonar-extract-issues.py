#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import pathlib
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request


def log(message: str) -> None:
    print(f"[sonar-extract] {message}", flush=True)


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def load_run_env(path: pathlib.Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value)
        except ValueError:
            parsed = [value]
        os.environ[key] = parsed[0] if parsed else ""


def latest_run_env() -> pathlib.Path | None:
    root = pathlib.Path("build/sonar-local")
    candidates = [path for path in root.glob("*/run.env") if path.is_file()]
    if (root / "run.env").is_file():
        candidates.append(root / "run.env")
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


if os.environ.get("SONAR_RUN_ENV"):
    load_run_env(pathlib.Path(os.environ["SONAR_RUN_ENV"]))
elif os.environ.get("SONAR_OUTPUT_DIR"):
    load_run_env(pathlib.Path(os.environ["SONAR_OUTPUT_DIR"]) / "run.env")
else:
    run_env = latest_run_env()
    if run_env is not None:
        load_run_env(run_env)


SONAR_PORT = os.environ.get("SONAR_PORT", "9000")
SONAR_URL = os.environ.get("SONAR_URL", f"http://127.0.0.1:{SONAR_PORT}")
SONAR_PROJECT_KEY = os.environ.get("SONAR_PROJECT_KEY", pathlib.Path.cwd().name)
SONAR_OUTPUT_DIR = pathlib.Path(os.environ.get("SONAR_OUTPUT_DIR", "build/sonar-local"))
SONAR_PAGE_SIZE = int(os.environ.get("SONAR_PAGE_SIZE", "500"))
SONAR_TOP_ISSUES = int(os.environ.get("SONAR_TOP_ISSUES", "30"))
SONAR_FETCH_ALL_ISSUES = os.environ.get("SONAR_FETCH_ALL_ISSUES", "true") == "true"
SONAR_HIGH_SEVERITIES = os.environ.get("SONAR_HIGH_SEVERITIES", "BLOCKER,CRITICAL")
SONAR_BUG_TYPES = os.environ.get("SONAR_BUG_TYPES", "BUG")
SONAR_MEASURES = os.environ.get(
    "SONAR_MEASURES",
    "bugs,vulnerabilities,code_smells,reliability_rating,security_rating,"
    "sqale_rating,ncloc,coverage,duplicated_lines_density",
)


def validate_page_size() -> None:
    if SONAR_PAGE_SIZE < 1 or SONAR_PAGE_SIZE > 500:
        die(f"SONAR_PAGE_SIZE must be between 1 and 500, got: {SONAR_PAGE_SIZE}", 2)


def auth_header(token: str) -> str:
    raw = f"{token}:".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request_json(
    path: str,
    *,
    params: dict[str, str] | None = None,
    token: str | None = None,
    method: str = "GET",
) -> dict:
    url = f"{SONAR_URL}{path}"
    data = None
    if params:
        encoded = urllib.parse.urlencode(params)
        if method == "GET":
            url = f"{url}?{encoded}"
        else:
            data = encoded.encode("utf-8")

    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("Authorization", auth_header(token))
    if method != "GET":
        request.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def token_is_valid(token: str) -> bool:
    try:
        response = request_json("/api/authentication/validate", token=token)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    return response.get("valid") is True


def token_candidates() -> list[pathlib.Path]:
    candidates: list[pathlib.Path] = []
    if os.environ.get("SONAR_TOKEN_FILE"):
        candidates.append(pathlib.Path(os.environ["SONAR_TOKEN_FILE"]))
    candidates.extend((SONAR_OUTPUT_DIR / "state").glob("*-token.txt"))
    if os.environ.get("SONAR_STATE_DIR"):
        candidates.extend(pathlib.Path(os.environ["SONAR_STATE_DIR"]).glob("*-token.txt"))
    candidates.extend((pathlib.Path.home() / ".codex/state/micronaut-sonar-review").glob("*-token.txt"))
    return candidates


def resolve_token() -> str:
    env_token = os.environ.get("SONAR_TOKEN")
    if env_token:
        if os.environ.get("SONAR_SKIP_TOKEN_VALIDATION") == "true" or token_is_valid(env_token):
            return env_token
        die(f"SONAR_TOKEN was provided but is not valid for {SONAR_URL}", 4)

    for candidate in token_candidates():
        if not candidate.is_file():
            continue
        token = candidate.read_text(encoding="utf-8").strip()
        if not token:
            continue
        if os.environ.get("SONAR_SKIP_TOKEN_VALIDATION") == "true" or token_is_valid(token):
            return token

    die(
        f"No valid Sonar token found for {SONAR_URL}.\n"
        "Set SONAR_TOKEN, SONAR_TOKEN_FILE, or run the local Sonar helper first.",
        4,
    )


def write_json(path: pathlib.Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch_base_results(token: str) -> None:
    log("Fetching issues, facets, quality gate, focused issue lists, and measures")
    write_json(
        SONAR_OUTPUT_DIR / "issues.json",
        request_json(
            "/api/issues/search",
            token=token,
            params={
                "componentKeys": SONAR_PROJECT_KEY,
                "resolved": "false",
                "ps": str(SONAR_PAGE_SIZE),
            },
        ),
    )
    write_json(
        SONAR_OUTPUT_DIR / "issues-facets.json",
        request_json(
            "/api/issues/search",
            token=token,
            params={
                "componentKeys": SONAR_PROJECT_KEY,
                "resolved": "false",
                "ps": "1",
                "facets": "severities,types",
            },
        ),
    )
    write_json(
        SONAR_OUTPUT_DIR / "issues-high.json",
        request_json(
            "/api/issues/search",
            token=token,
            params={
                "componentKeys": SONAR_PROJECT_KEY,
                "resolved": "false",
                "severities": SONAR_HIGH_SEVERITIES,
                "ps": str(SONAR_PAGE_SIZE),
            },
        ),
    )
    write_json(
        SONAR_OUTPUT_DIR / "issues-bugs.json",
        request_json(
            "/api/issues/search",
            token=token,
            params={
                "componentKeys": SONAR_PROJECT_KEY,
                "resolved": "false",
                "types": SONAR_BUG_TYPES,
                "ps": str(SONAR_PAGE_SIZE),
            },
        ),
    )
    write_json(
        SONAR_OUTPUT_DIR / "quality-gate.json",
        request_json(
            "/api/qualitygates/project_status",
            token=token,
            params={"projectKey": SONAR_PROJECT_KEY},
        ),
    )
    try:
        write_json(
            SONAR_OUTPUT_DIR / "measures.json",
            request_json(
                "/api/measures/component",
                token=token,
                params={"component": SONAR_PROJECT_KEY, "metricKeys": SONAR_MEASURES},
            ),
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass


def fetch_all_issue_pages(token: str) -> None:
    if not SONAR_FETCH_ALL_ISSUES:
        return

    log("Fetching all unresolved issue pages")
    pages_dir = SONAR_OUTPUT_DIR / "issues-pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    issues: list[dict] = []
    total = 0
    page = 1
    while True:
        payload = request_json(
            "/api/issues/search",
            token=token,
            params={
                "componentKeys": SONAR_PROJECT_KEY,
                "resolved": "false",
                "p": str(page),
                "ps": str(SONAR_PAGE_SIZE),
            },
        )
        write_json(pages_dir / f"issues-{page}.json", payload)
        page_issues = payload.get("issues", [])
        total = max(total, int(payload.get("total", 0)))
        if not page_issues:
            break
        issues.extend(page_issues)
        if page * SONAR_PAGE_SIZE >= total:
            break
        page += 1

    write_json(
        SONAR_OUTPUT_DIR / "issues-all.json",
        {
            "componentKey": SONAR_PROJECT_KEY,
            "issues": issues,
            "returned": len(issues),
            "total": total,
        },
    )


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_summary() -> None:
    log("Writing summary")
    issues_path = SONAR_OUTPUT_DIR / "issues-all.json"
    if not issues_path.exists():
        issues_path = SONAR_OUTPUT_DIR / "issues.json"

    issues = read_json(issues_path)
    facets = read_json(SONAR_OUTPUT_DIR / "issues-facets.json")
    quality_gate = read_json(SONAR_OUTPUT_DIR / "quality-gate.json")
    measures: dict[str, str] = {}
    measures_path = SONAR_OUTPUT_DIR / "measures.json"
    if measures_path.exists():
        try:
            data = read_json(measures_path)
            measures = {
                item.get("metric", ""): item.get("value", "")
                for item in data.get("component", {}).get("measures", [])
            }
        except json.JSONDecodeError:
            measures = {}

    facet_counts = {
        facet.get("property", ""): {
            value.get("val", ""): value.get("count", 0)
            for value in facet.get("values", [])
        }
        for facet in facets.get("facets", [])
    }

    issue_items = issues.get("issues", [])
    lines = [
        f"PROJECT_KEY={SONAR_PROJECT_KEY}",
        f"QUALITY_GATE={quality_gate.get('projectStatus', {}).get('status', 'UNKNOWN')}",
        f"ISSUES_TOTAL={issues.get('total', len(issue_items))}",
        f"ISSUES_RETURNED={len(issue_items)}",
    ]
    for severity, count in sorted(facet_counts.get("severities", {}).items()):
        lines.append(f"ISSUES_SEVERITY_{severity}={count}")
    for issue_type, count in sorted(facet_counts.get("types", {}).items()):
        lines.append(f"ISSUES_TYPE_{issue_type}={count}")
    for metric in sorted(measures):
        if metric:
            lines.append(f"MEASURE_{metric.upper()}={measures[metric]}")

    if issue_items:
        lines.append("")
        lines.append("TOP_ISSUES=")
        for item in issue_items[:SONAR_TOP_ISSUES]:
            component = item.get("component", "")
            line = item.get("line")
            location = f"{component}:{line}" if line else component
            message = item.get("message", "").replace("\n", " ")
            lines.append(
                f"- {item.get('severity', 'UNKNOWN')} {item.get('type', 'UNKNOWN')} "
                f"{location} {message}"
            )

    summary = "\n".join(lines) + "\n"
    (SONAR_OUTPUT_DIR / "summary.txt").write_text(summary, encoding="utf-8")
    print(summary, end="")


def main() -> None:
    validate_page_size()
    SONAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    token = resolve_token()
    log(f"Extracting SonarQube results for {SONAR_PROJECT_KEY} from {SONAR_URL}")
    fetch_base_results(token)
    fetch_all_issue_pages(token)
    write_summary()


if __name__ == "__main__":
    main()
