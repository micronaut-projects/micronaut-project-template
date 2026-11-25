#!/usr/bin/env python3
"""Computes the risk tier of a pull request from its changed paths, and labels it.

The tiers are described in MAINTAINING.md, under "Risk tiers and AI disclosure":

* T0: build, docs, tests and synced files. Nothing published changes.
* T1: internal module code.
* T2: public API, inject, core-processor, serialization, security, HTTP, or anything breaking.

Each changed file gets a tier, and the highest one wins. A file is T2 when it matches a ``t2`` glob of the
repository's ``.github/risk-tiers.yml``, T0 when it matches the default T0 map or a ``t0`` glob of that file, and T1
otherwise. ``gradle/libs.versions.toml`` is T1, because a version bump can change published dependencies. The
``type: breaking`` label, or "API or behaviour change: yes" in the pull request body, raise the tier to T2.

The computed tier is a floor, not the final word: no script can see every risk in a change, so the AI reviewer
double-checks it. When the reviewer, or a maintainer, sets a higher ``tier: ...`` label, the script keeps it and
never lowers it. Only tier labels this workflow added itself are replaced.

The script also reads the "Review declaration" lines of the pull request template. When the declared tier is lower
than the computed one, the check fails. When AI use is declared as assisted or agent-generated, the matching
``ai: ...`` label is added.

It runs from a ``pull_request_target`` workflow, so it never checks out or runs pull request code: it reads the
changed paths and the body through the GitHub API, and ``.github/risk-tiers.yml`` from the base branch checkout.

Only the Python standard library is used. ``risk-tiers.yml`` supports a small YAML subset: top-level ``t0:`` and
``t2:`` keys, each followed by a list of ``- "glob"`` items, plus comments.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TIERS = ("T0", "T1", "T2")

# Paths that never change what is published: tests, docs, build logic and the files synced from the template.
DEFAULT_T0_GLOBS = (
    "**/src/test/**",
    "**/src/testFixtures/**",
    "test-suite*/**",
    "tests/**",
    "doc-examples/**",
    "src/main/docs/**",
    "*.md",
    "*.adoc",
    "gradle/**",
    "buildSrc/**",
    ".github/**",
    ".agents/**",
    ".claude/**",
    "config/**",
    ".clineignore",
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".sdkmanrc",
    "gradlew",
    "gradlew.bat",
    "LICENSE",
)

# Paths that would be T0 by the map above, but can change published artifacts.
DEFAULT_T1_GLOBS = (
    "gradle/libs.versions.toml",
)

TIER_LABELS = {tier: f"tier: {tier}" for tier in TIERS}
AI_LABELS = {"assisted": "ai: assisted", "agent-generated": "ai: agent-generated"}
BREAKING_LABEL = "type: breaking"
# The login GITHUB_TOKEN acts as. Tier labels added by anyone else are overrides the script keeps.
WORKFLOW_ACTOR = "github-actions[bot]"

# Footers and banners that AI tools add to pull request descriptions. The review declaration already records AI use,
# so the template asks for none of them, whichever agent or harness wrote the pull request.
TOOL_FOOTER_PATTERNS = (
    r"generated (?:with|by) \[?(?:claude|codex|copilot|cursor|chatgpt|gemini|devin|openai|anthropic)",
    r"made with \[?cursor",
    r"co-authored-by:.*(?:claude|anthropic|copilot|cursor|codex|openai|devin)",
    r"claude\.ai/code/session_",
    r"^\s*\U0001F916",
)

DECLARATION_FIELDS = {
    "ai_use": ("ai use", ("none", "assisted", "agent-generated")),
    "ai_tool": ("ai tool", None),
    "risk_tier": ("risk tier", TIERS),
    "api_change": ("api or behaviour change", ("yes", "no")),
}


def glob_to_regex(glob):
    """Translates a gitignore-style glob to a regular expression.

    ``**`` matches any number of directories, ``*`` and ``?`` do not cross ``/``. A glob without ``/`` matches the
    file name at any depth, like ``*.md``. A glob ending in ``/`` matches everything below that directory.
    """
    glob = glob.strip()
    if glob.endswith("/"):
        glob += "**"
    anchored = "/" in glob.rstrip("/")
    glob = glob.lstrip("/")
    regex = ""
    i = 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            regex += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            regex += ".*"
            i += 2
        elif c == "*":
            regex += "[^/]*"
            i += 1
        elif c == "?":
            regex += "[^/]"
            i += 1
        else:
            regex += re.escape(c)
            i += 1
    if not anchored:
        regex = "(?:.*/)?" + regex
    return re.compile(regex + r"\Z")


def matches_any(path, globs):
    return any(glob_to_regex(glob).match(path) for glob in globs)


def parse_tiers_file(text):
    """Parses the subset of YAML used by .github/risk-tiers.yml into {"t0": [...], "t2": [...]}."""
    result = {"t0": [], "t2": []}
    current = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        key = re.fullmatch(r"([A-Za-z0-9_]+):\s*(\[\s*\])?", line)
        if key:
            current = key.group(1).lower()
            if current not in result:
                raise ValueError(f"risk-tiers.yml line {number}: unknown key '{key.group(1)}', expected t0 or t2")
            continue
        item = re.fullmatch(r"\s+-\s+(.+)", line)
        if item and current:
            value = item.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            result[current].append(value)
            continue
        raise ValueError(f"risk-tiers.yml line {number}: cannot parse '{raw}'")
    return result


def file_tier(path, config):
    if matches_any(path, config["t2"]):
        return "T2"
    if matches_any(path, DEFAULT_T1_GLOBS):
        return "T1"
    if matches_any(path, DEFAULT_T0_GLOBS) or matches_any(path, config["t0"]):
        return "T0"
    return "T1"


def parse_declaration(body):
    """Reads the "Review declaration" of a pull request body.

    Each field is a table row "| key | value |", as in the template, or a line "key: value". Keys are case-insensitive
    and HTML comments are ignored. A value that is not one of the allowed options, such as an unedited "T0 / T1 / T2",
    counts as not declared (None).
    """
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL)
    result = {name: None for name in DECLARATION_FIELDS}
    for line in body.splitlines():
        for name, (key, options) in DECLARATION_FIELDS.items():
            match = (re.match(rf"\s*\|\s*\**{re.escape(key)}\**\s*\|\s*(.*?)\s*\|?\s*$", line, flags=re.IGNORECASE)
                     or re.match(rf"\s*(?:[-*]\s+)?\**{re.escape(key)}\**\s*:\**\s*(.*)$", line, flags=re.IGNORECASE))
            if not match or result[name] is not None:
                continue
            value = match.group(1).strip().strip("`*").strip()
            if options is None:
                result[name] = value if value and value.lower() not in ("n/a", "none", "-") else None
            else:
                normalised = value.upper() if options is TIERS else value.lower()
                result[name] = normalised if normalised in options else None
    return result


def tool_footers(body):
    """Returns the lines of a pull request body that look like an AI tool footer or banner, ignoring HTML comments."""
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL)
    return [line.strip() for line in body.splitlines()
            if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in TOOL_FOOTER_PATTERNS)]


def compute(paths, labels, body, config):
    """Returns the computed tier, the declaration, and the reasons for the tier."""
    declaration = parse_declaration(body)
    per_tier = {tier: [] for tier in TIERS}
    for path in paths:
        per_tier[file_tier(path, config)].append(path)
    tier = max((t for t in TIERS if per_tier[t]), default="T0", key=TIERS.index)
    reasons = []
    if per_tier[tier]:
        reasons.append(f"{len(per_tier[tier])} changed file(s) are {tier}")
    if BREAKING_LABEL in labels:
        tier = "T2"
        reasons.append(f"labelled '{BREAKING_LABEL}'")
    if declaration["api_change"] == "yes":
        tier = "T2"
        reasons.append("declares an API or behaviour change")
    return {
        "tier": tier,
        "files": per_tier,
        "reasons": reasons,
        "declaration": declaration,
        "override": None,
        "footers": tool_footers(body),
        "declared_too_low": declaration["risk_tier"] is not None
        and TIERS.index(declaration["risk_tier"]) < TIERS.index(tier),
    }


def override_tier(events, labels, workflow_actor=WORKFLOW_ACTOR):
    """Returns the highest tier label on the pull request that someone other than this workflow added, or None.

    ``events`` are the issue events of the pull request, oldest first, and ``labels`` its current label names. The
    last ``labeled`` event of a label tells who added it.
    """
    added_by = {}
    for event in events:
        if event.get("event") == "labeled" and event.get("label"):
            added_by[event["label"]["name"]] = (event.get("actor") or {}).get("login")
    overrides = [tier for tier, name in TIER_LABELS.items()
                 if name in labels and added_by.get(name) not in (None, workflow_actor)]
    return max(overrides, key=TIERS.index, default=None)


class GitHub:
    def __init__(self, token, repository, api_url="https://api.github.com"):
        self.token = token
        self.repository = repository
        self.api_url = api_url.rstrip("/")

    def request(self, method, path, data=None):
        url = path if path.startswith("http") else f"{self.api_url}/repos/{self.repository}/{path}"
        request = urllib.request.Request(url, method=method, data=None if data is None else json.dumps(data).encode())
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            link = response.headers.get("Link", "")
        return (json.loads(payload) if payload else None), link

    def paginate(self, path):
        separator = "&" if "?" in path else "?"
        url = f"{path}{separator}per_page=100"
        items = []
        while url:
            page, link = self.request("GET", url)
            items.extend(page)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        return items

    def changed_paths(self, number):
        paths = []
        for change in self.paginate(f"pulls/{number}/files"):
            paths.append(change["filename"])
            if change.get("previous_filename"):
                paths.append(change["previous_filename"])
        return paths

    def events(self, number):
        return self.paginate(f"issues/{number}/events")

    def label_exists(self, name):
        try:
            self.request("GET", f"labels/{urllib.parse.quote(name, safe='')}")
            return True
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return False
            raise

    def add_label(self, number, name):
        self.request("POST", f"issues/{number}/labels", {"labels": [name]})

    def remove_label(self, number, name):
        try:
            self.request("DELETE", f"issues/{number}/labels/{urllib.parse.quote(name, safe='')}")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise


def sync_labels(github, number, current, wanted, managed):
    """Adds the wanted labels and removes the other managed ones. Labels missing from the repository are skipped,
    so the script never creates them: they are managed in micronaut-projects/management."""
    warnings = []
    for name in sorted(managed - wanted):
        if name in current:
            github.remove_label(number, name)
    for name in sorted(wanted - current):
        if github.label_exists(name):
            github.add_label(number, name)
        else:
            warnings.append(f"Label '{name}' does not exist in this repository, so it was not added.")
    return warnings


def summary(result, warnings):
    declaration = result["declaration"]
    lines = [
        f"## Risk tier: {result['tier']}",
        "",
        "Why: " + ("; ".join(result["reasons"]) or "no changed files") + ".",
        "",
        f"Declared tier: {declaration['risk_tier'] or 'not declared'}. "
        f"AI use: {declaration['ai_use'] or 'not declared'}. "
        f"API or behaviour change: {declaration['api_change'] or 'not declared'}.",
        "",
    ]
    if result["declared_too_low"]:
        lines += [
            f"The pull request declares {declaration['risk_tier']}, but its changes are {result['tier']}. "
            f"Change the 'Risk tier' line of the description to {result['tier']}.",
            "",
        ]
    if result["footers"]:
        lines += ["The description has AI tool footers or banners. Remove them: the review declaration already records "
                  "AI use.", ""] + [f"- `{line}`" for line in result["footers"]] + [""]
    for tier in reversed(TIERS):
        files = result["files"][tier]
        if files:
            lines.append(f"<details><summary>{tier}: {len(files)} file(s)</summary>\n")
            lines += [f"- `{path}`" for path in files[:200]]
            if len(files) > 200:
                lines.append(f"- ... and {len(files) - 200} more")
            lines.append("\n</details>\n")
    lines += [f"> [!WARNING]\n> {warning}\n" for warning in warnings]
    return "\n".join(lines)


def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as tiers_file:
            return parse_tiers_file(tiers_file.read())
    return {"t0": [], "t2": []}


def run_event(args):
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        event = json.load(event_file)
    pull_request = event["pull_request"]
    number = pull_request["number"]
    github = GitHub(os.environ.get("GITHUB_TOKEN"), os.environ["GITHUB_REPOSITORY"],
                    os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    config = load_config(args.config)
    labels = {label["name"] for label in pull_request.get("labels", [])}
    result = compute(github.changed_paths(number), labels, pull_request.get("body"), config)

    override = override_tier(github.events(number), labels)
    if override and TIERS.index(override) > TIERS.index(result["tier"]):
        result["override"] = override
        result["reasons"].append(f"a reviewer or maintainer raised it to {override}")
        result["tier"] = override
    wanted = {TIER_LABELS[result["tier"]]}
    ai_use = result["declaration"]["ai_use"]
    if ai_use in AI_LABELS:
        wanted.add(AI_LABELS[ai_use])
    managed = set(TIER_LABELS.values()) | set(AI_LABELS.values())
    if ai_use is None:
        # Not declared: keep any AI label a maintainer or the reviewer set by hand.
        managed -= set(AI_LABELS.values())
        wanted |= labels & set(AI_LABELS.values())
    warnings = [] if args.dry_run else sync_labels(github, number, labels, wanted, managed)

    text = summary(result, warnings)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary_file:
            summary_file.write(text + "\n")
    failed = False
    if result["footers"]:
        print("::error title=AI tool footer in the description::Remove the tool footers or banners from the pull request "
              "description. The review declaration already records AI use.")
        failed = True
    if result["declared_too_low"]:
        failed = True
        print(f"::error title=Declared risk tier too low::The pull request declares {result['declaration']['risk_tier']}"
              f", but its changes are {result['tier']}. Update the 'Risk tier' line of the description.")
    return 1 if failed else 0


def run_replay(args):
    """Computes the tiers of the pull requests merged since a date, without labelling them."""
    github = GitHub(args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"), args.repository)
    config = load_config(args.config)
    counts = {tier: 0 for tier in TIERS}
    rows = []
    for pull_request in github.paginate("pulls?state=closed&sort=updated&direction=desc"):
        if pull_request["updated_at"][:10] < args.since:
            break
        merged = pull_request.get("merged_at")
        if not merged or merged[:10] < args.since or (args.until and merged[:10] > args.until):
            continue
        labels = {label["name"] for label in pull_request.get("labels", [])}
        result = compute(github.changed_paths(pull_request["number"]), labels, pull_request.get("body"), config)
        counts[result["tier"]] += 1
        rows.append({"number": pull_request["number"], "title": pull_request["title"],
                     "author": pull_request["user"]["login"], "base": pull_request["base"]["ref"],
                     "tier": result["tier"], "reasons": result["reasons"]})
    print(json.dumps({"repository": args.repository, "since": args.since, "until": args.until,
                      "counts": counts, "pull_requests": rows}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--config", default=".github/risk-tiers.yml", help="path to the risk-tiers.yml file")
    sub = parser.add_subparsers(dest="command", required=True)
    event = sub.add_parser("event", help="label the pull request of the current GitHub Actions event")
    event.add_argument("--dry-run", action="store_true", help="compute and report, without changing labels")
    replay = sub.add_parser("replay", help="compute the tiers of merged pull requests, without labelling them")
    replay.add_argument("repository", help="owner/name")
    replay.add_argument("--since", required=True, help="first merge date, YYYY-MM-DD")
    replay.add_argument("--until", help="last merge date, YYYY-MM-DD")
    replay.add_argument("--token", help="GitHub token, defaults to GITHUB_TOKEN or GH_TOKEN")
    args = parser.parse_args(argv)
    return run_event(args) if args.command == "event" else run_replay(args)


if __name__ == "__main__":
    sys.exit(main())
