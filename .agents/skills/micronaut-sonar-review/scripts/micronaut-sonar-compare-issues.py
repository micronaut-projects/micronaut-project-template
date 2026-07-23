#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from collections.abc import Iterable


SEVERITY_RANK = {
    "INFO": 0,
    "MINOR": 1,
    "MAJOR": 2,
    "CRITICAL": 3,
    "BLOCKER": 4,
}


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def read_json(path: pathlib.Path, default: dict | None = None) -> dict:
    if not path.is_file():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_message(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def issue_location(issue: dict) -> str:
    component = str(issue.get("component", ""))
    line = issue.get("line")
    return f"{component}:{line}" if line else component


def issue_brief(issue: dict) -> str:
    message = normalize_message(str(issue.get("message", "")))
    return (
        f"{issue.get('severity', 'UNKNOWN')} {issue.get('type', 'UNKNOWN')} "
        f"{issue_location(issue)} {issue.get('rule', '')} {message}"
    ).strip()


def issue_group_key(issue: dict) -> tuple[str, str, str, str]:
    return (
        str(issue.get("type", "UNKNOWN")),
        str(issue.get("severity", "UNKNOWN")),
        str(issue.get("rule", "")),
        normalize_message(str(issue.get("message", ""))),
    )


def group_issues(issues: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for issue in issues:
        groups.setdefault(issue_group_key(issue), []).append(issue)

    result: list[dict] = []
    for (issue_type, severity, rule, message), items in groups.items():
        result.append(
            {
                "type": issue_type,
                "severity": severity,
                "rule": rule,
                "message": message,
                "count": len(items),
                "issues": sorted(items, key=lambda item: (str(item.get("component", "")), int(item.get("line", 0) or 0))),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            -SEVERITY_RANK.get(item["severity"], -1),
            item["type"],
            item["rule"],
            item["message"],
        ),
    )


def group_title(group: dict) -> str:
    return (
        f"{group['severity']} {group['type']} {group['rule']} "
        f"count={group['count']} {group['message']}"
    ).strip()


def issue_identity(issue: dict, mode: str) -> str:
    if mode == "key":
        key = issue.get("key")
        if key:
            return f"key:{key}"
    parts = [
        str(issue.get("component", "")),
        str(issue.get("line", "")),
        str(issue.get("rule", "")),
        normalize_message(str(issue.get("message", ""))),
    ]
    return "fingerprint:" + "\u241f".join(parts)


def issue_key_set(issues: Iterable[dict]) -> set[str]:
    return {str(issue["key"]) for issue in issues if issue.get("key")}


def choose_identity_mode(baseline: list[dict], current: list[dict], requested: str) -> str:
    if requested != "auto":
        return requested
    baseline_keys = issue_key_set(baseline)
    current_keys = issue_key_set(current)
    return "key" if baseline_keys & current_keys else "fingerprint"


def issues_from(path: pathlib.Path) -> list[dict]:
    payload = read_json(path)
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        return []
    return [issue for issue in issues if isinstance(issue, dict)]


def issue_total(path: pathlib.Path) -> int:
    payload = read_json(path)
    if "total" in payload:
        try:
            return int(payload["total"])
        except (TypeError, ValueError):
            pass
    return len(payload.get("issues", []))


def all_issues_path(directory: pathlib.Path) -> pathlib.Path:
    path = directory / "issues-all.json"
    return path if path.is_file() else directory / "issues.json"


def facet_counts(directory: pathlib.Path) -> dict[str, dict[str, int]]:
    payload = read_json(directory / "issues-facets.json")
    result: dict[str, dict[str, int]] = {}
    for facet in payload.get("facets", []):
        prop = facet.get("property")
        if not prop:
            continue
        result[prop] = {}
        for value in facet.get("values", []):
            key = value.get("val")
            if key is None:
                continue
            result[prop][str(key)] = int(value.get("count", 0))
    return result


def quality_gate(directory: pathlib.Path) -> str:
    payload = read_json(directory / "quality-gate.json")
    return str(payload.get("projectStatus", {}).get("status", "UNKNOWN"))


def compare_counts(baseline: dict[str, int], current: dict[str, int]) -> dict[str, dict[str, int]]:
    keys = sorted(set(baseline) | set(current))
    return {
        key: {
            "baseline": baseline.get(key, 0),
            "current": current.get(key, 0),
            "delta": current.get(key, 0) - baseline.get(key, 0),
        }
        for key in keys
    }


def index_issues(issues: list[dict], mode: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for issue in issues:
        indexed.setdefault(issue_identity(issue, mode), issue)
    return indexed


def is_worsened(baseline: dict, current: dict) -> bool:
    baseline_severity = SEVERITY_RANK.get(str(baseline.get("severity", "")), -1)
    current_severity = SEVERITY_RANK.get(str(current.get("severity", "")), -1)
    if current_severity > baseline_severity:
        return True
    return baseline.get("type") != "BUG" and current.get("type") == "BUG"


def compare_issue_list(
    baseline_issues: list[dict],
    current_issues: list[dict],
    mode: str,
    top: int,
) -> dict:
    baseline_index = index_issues(baseline_issues, mode)
    current_index = index_issues(current_issues, mode)
    baseline_ids = set(baseline_index)
    current_ids = set(current_index)
    new_ids = sorted(current_ids - baseline_ids)
    resolved_ids = sorted(baseline_ids - current_ids)
    common_ids = sorted(baseline_ids & current_ids)
    worsened_ids = [
        issue_id
        for issue_id in common_ids
        if is_worsened(baseline_index[issue_id], current_index[issue_id])
    ]
    changed_ids = [
        issue_id
        for issue_id in common_ids
        if (
            baseline_index[issue_id].get("severity") != current_index[issue_id].get("severity")
            or baseline_index[issue_id].get("type") != current_index[issue_id].get("type")
        )
    ]

    return {
        "baseline_returned": len(baseline_issues),
        "current_returned": len(current_issues),
        "new_count": len(new_ids),
        "resolved_count": len(resolved_ids),
        "common_count": len(common_ids),
        "changed_count": len(changed_ids),
        "worsened_count": len(worsened_ids),
        "new": [current_index[issue_id] for issue_id in new_ids[:top]],
        "resolved": [baseline_index[issue_id] for issue_id in resolved_ids[:top]],
        "changed": [
            {"baseline": baseline_index[issue_id], "current": current_index[issue_id]}
            for issue_id in changed_ids[:top]
        ],
        "worsened": [
            {"baseline": baseline_index[issue_id], "current": current_index[issue_id]}
            for issue_id in worsened_ids[:top]
        ],
        "new_groups": group_issues([current_index[issue_id] for issue_id in new_ids]),
    }


def append_new_groups(lines: list[str], payload: dict, kind: str, title: str, top: int) -> None:
    groups = payload["issues"][kind]["new_groups"]
    lines.append("")
    lines.append(f"{title}={len(groups)}")
    for group in groups[:top]:
        lines.append(f"- {group_title(group)}")
        for issue in group["issues"][:top]:
            lines.append(f"  - {issue_location(issue)}")


def summary_lines(payload: dict, top: int) -> list[str]:
    lines = [
        f"BASELINE_DIR={payload['baseline_dir']}",
        f"CURRENT_DIR={payload['current_dir']}",
        f"IDENTITY_MODE={payload['identity_mode']}",
        f"BASELINE_QUALITY_GATE={payload['quality_gate']['baseline']}",
        f"CURRENT_QUALITY_GATE={payload['quality_gate']['current']}",
        f"QUALITY_GATE_CHANGED={str(payload['quality_gate']['changed']).lower()}",
        f"ISSUES_TOTAL_BASELINE={payload['totals']['all']['baseline']}",
        f"ISSUES_TOTAL_CURRENT={payload['totals']['all']['current']}",
        f"ISSUES_TOTAL_DELTA={payload['totals']['all']['delta']}",
        f"BUGS_TOTAL_BASELINE={payload['totals']['bugs']['baseline']}",
        f"BUGS_TOTAL_CURRENT={payload['totals']['bugs']['current']}",
        f"BUGS_TOTAL_DELTA={payload['totals']['bugs']['delta']}",
        f"HIGH_TOTAL_BASELINE={payload['totals']['high']['baseline']}",
        f"HIGH_TOTAL_CURRENT={payload['totals']['high']['current']}",
        f"HIGH_TOTAL_DELTA={payload['totals']['high']['delta']}",
        f"NEW_ISSUES={payload['issues']['all']['new_count']}",
        f"RESOLVED_ISSUES={payload['issues']['all']['resolved_count']}",
        f"WORSENED_ISSUES={payload['issues']['all']['worsened_count']}",
        f"NEW_BUGS={payload['issues']['bugs']['new_count']}",
        f"RESOLVED_BUGS={payload['issues']['bugs']['resolved_count']}",
        f"WORSENED_BUGS={payload['issues']['bugs']['worsened_count']}",
        f"NEW_HIGH_ISSUES={payload['issues']['high']['new_count']}",
        f"RESOLVED_HIGH_ISSUES={payload['issues']['high']['resolved_count']}",
        f"WORSENED_HIGH_ISSUES={payload['issues']['high']['worsened_count']}",
    ]

    append_new_groups(lines, payload, "bugs", "NEW_BUG_GROUPS", top)
    append_new_groups(lines, payload, "high", "NEW_HIGH_GROUPS", top)
    append_new_groups(lines, payload, "all", "NEW_ISSUE_GROUPS", top)

    worsened = payload["issues"]["all"]["worsened"]
    if worsened:
        lines.append("")
        lines.append("WORSENED_ISSUE_DETAILS=")
        for item in worsened[:top]:
            lines.append(f"- before: {issue_brief(item['baseline'])}")
            lines.append(f"  after:  {issue_brief(item['current'])}")

    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two extracted local SonarQube issue directories.")
    parser.add_argument("--baseline", default=os.environ.get("SONAR_BASELINE_DIR"), help="Baseline Sonar output dir")
    parser.add_argument("--current", default=os.environ.get("SONAR_CURRENT_DIR"), help="Current Sonar output dir")
    parser.add_argument(
        "--output",
        default=os.environ.get("SONAR_COMPARE_OUTPUT_DIR"),
        help="Directory for compare.json and compare-summary.txt",
    )
    parser.add_argument(
        "--identity",
        choices=("auto", "key", "fingerprint"),
        default=os.environ.get("SONAR_COMPARE_IDENTITY", "auto"),
        help="Issue identity strategy. auto uses Sonar keys when runs share keys; otherwise fingerprints.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=int(os.environ.get("SONAR_COMPARE_TOP", "30")),
        help="Maximum issue details to include per section",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.baseline:
        die("Set --baseline or SONAR_BASELINE_DIR.")
    if not args.current:
        die("Set --current or SONAR_CURRENT_DIR.")

    baseline_dir = pathlib.Path(args.baseline)
    current_dir = pathlib.Path(args.current)
    if not baseline_dir.is_dir():
        die(f"Baseline directory does not exist: {baseline_dir}", 2)
    if not current_dir.is_dir():
        die(f"Current directory does not exist: {current_dir}", 2)

    output_dir = pathlib.Path(args.output) if args.output else current_dir / "sonar-compare"
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_all = issues_from(all_issues_path(baseline_dir))
    current_all = issues_from(all_issues_path(current_dir))
    mode = choose_identity_mode(baseline_all, current_all, args.identity)

    baseline_facets = facet_counts(baseline_dir)
    current_facets = facet_counts(current_dir)
    baseline_quality = quality_gate(baseline_dir)
    current_quality = quality_gate(current_dir)

    baseline_totals = {
        "all": issue_total(all_issues_path(baseline_dir)),
        "bugs": issue_total(baseline_dir / "issues-bugs.json"),
        "high": issue_total(baseline_dir / "issues-high.json"),
    }
    current_totals = {
        "all": issue_total(all_issues_path(current_dir)),
        "bugs": issue_total(current_dir / "issues-bugs.json"),
        "high": issue_total(current_dir / "issues-high.json"),
    }

    payload = {
        "baseline_dir": str(baseline_dir),
        "current_dir": str(current_dir),
        "identity_mode": mode,
        "quality_gate": {
            "baseline": baseline_quality,
            "current": current_quality,
            "changed": baseline_quality != current_quality,
        },
        "totals": {
            key: {
                "baseline": baseline_totals[key],
                "current": current_totals[key],
                "delta": current_totals[key] - baseline_totals[key],
            }
            for key in ("all", "bugs", "high")
        },
        "facets": {
            "severities": compare_counts(
                baseline_facets.get("severities", {}),
                current_facets.get("severities", {}),
            ),
            "types": compare_counts(
                baseline_facets.get("types", {}),
                current_facets.get("types", {}),
            ),
        },
        "issues": {
            "all": compare_issue_list(baseline_all, current_all, mode, args.top),
            "bugs": compare_issue_list(
                issues_from(baseline_dir / "issues-bugs.json"),
                issues_from(current_dir / "issues-bugs.json"),
                mode,
                args.top,
            ),
            "high": compare_issue_list(
                issues_from(baseline_dir / "issues-high.json"),
                issues_from(current_dir / "issues-high.json"),
                mode,
                args.top,
            ),
        },
    }

    write_json(output_dir / "compare.json", payload)
    summary = "\n".join(summary_lines(payload, args.top)) + "\n"
    (output_dir / "compare-summary.txt").write_text(summary, encoding="utf-8")
    print(summary, end="")
    print(f"[sonar-compare] Wrote {output_dir / 'compare.json'}")
    print(f"[sonar-compare] Wrote {output_dir / 'compare-summary.txt'}")


if __name__ == "__main__":
    main()
