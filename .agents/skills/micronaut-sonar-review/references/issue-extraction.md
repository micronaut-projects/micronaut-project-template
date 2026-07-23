# Issue Extraction

Prefer the bundled extractor after a Sonar analysis has been uploaded:

```bash
SONAR_RUN_ENV=build/sonar-local/<run-id>/run.env \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-extract-issues.sh
```

The shell wrapper delegates to `micronaut-sonar-extract-issues.py`; call the Python file directly if a shell wrapper is inconvenient.

## Outputs

The extractor writes these files under `SONAR_OUTPUT_DIR`:

- `issues.json`: first unresolved issue page
- `issues-all.json`: combined unresolved issues from every fetched page
- `issues-pages/`: raw paginated issue responses
- `issues-facets.json`: exact aggregate counts by severity and type
- `issues-high.json`: `BLOCKER` and `CRITICAL` issues by default
- `issues-bugs.json`: bug issues by default
- `quality-gate.json`: quality-gate status
- `measures.json`: project measures where available
- `summary.txt`: compact review summary

## Environment

Useful overrides:

```bash
SONAR_RUN_ENV=build/sonar-local/<run-id>/run.env
SONAR_PROJECT_KEY=micronaut-sourcegen
SONAR_OUTPUT_DIR=build/sonar-local/<run-id>
SONAR_TOKEN=<token>
SONAR_TOKEN_FILE=build/sonar-local/<run-id>/state/token.txt
SONAR_FETCH_ALL_ISSUES=false
SONAR_PAGE_SIZE=500
SONAR_TOP_ISSUES=30
SONAR_HIGH_SEVERITIES=BLOCKER,CRITICAL
SONAR_BUG_TYPES=BUG
```

The local Sonar API page size is limited to 500. Use Sonar's facets API to get exact aggregate counts, then fetch focused issue sets for review.

## Manual API Calls

Set common values first when not using `run.env`:

```bash
SONAR_URL="${SONAR_URL:?set SONAR_URL from run.env}"
SONAR_PROJECT_KEY="${SONAR_PROJECT_KEY:-$(basename "$PWD")}"
SONAR_OUTPUT_DIR="${SONAR_OUTPUT_DIR:-build/sonar-local/manual}"
TOKEN="${SONAR_TOKEN:-$(cat "$SONAR_TOKEN_FILE")}"
mkdir -p "$SONAR_OUTPUT_DIR"
```

Extract unresolved issues, quality gate, and exact severity/type counts:

```bash
curl -fsS -u "$TOKEN:" --get \
  --data-urlencode "componentKeys=$SONAR_PROJECT_KEY" \
  --data-urlencode "resolved=false" \
  --data-urlencode "ps=500" \
  "$SONAR_URL/api/issues/search" \
  > "$SONAR_OUTPUT_DIR/issues.json"

curl -fsS -u "$TOKEN:" --get \
  --data-urlencode "projectKey=$SONAR_PROJECT_KEY" \
  "$SONAR_URL/api/qualitygates/project_status" \
  > "$SONAR_OUTPUT_DIR/quality-gate.json"

curl -fsS -u "$TOKEN:" --get \
  --data-urlencode "componentKeys=$SONAR_PROJECT_KEY" \
  --data-urlencode "resolved=false" \
  --data-urlencode "ps=1" \
  --data-urlencode "facets=severities,types" \
  "$SONAR_URL/api/issues/search" \
  > "$SONAR_OUTPUT_DIR/issues-facets.json"
```

Extract targeted lists for review:

```bash
curl -fsS -u "$TOKEN:" --get \
  --data-urlencode "componentKeys=$SONAR_PROJECT_KEY" \
  --data-urlencode "resolved=false" \
  --data-urlencode "severities=BLOCKER,CRITICAL" \
  --data-urlencode "ps=200" \
  "$SONAR_URL/api/issues/search" \
  > "$SONAR_OUTPUT_DIR/issues-high.json"

curl -fsS -u "$TOKEN:" --get \
  --data-urlencode "componentKeys=$SONAR_PROJECT_KEY" \
  --data-urlencode "resolved=false" \
  --data-urlencode "types=BUG" \
  --data-urlencode "ps=200" \
  "$SONAR_URL/api/issues/search" \
  > "$SONAR_OUTPUT_DIR/issues-bugs.json"
```

Create a compact issue summary from the extracted files:

```bash
python3 - "$SONAR_OUTPUT_DIR" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
issues = json.loads((out / "issues.json").read_text(encoding="utf-8"))
facets = json.loads((out / "issues-facets.json").read_text(encoding="utf-8"))
quality_gate = json.loads((out / "quality-gate.json").read_text(encoding="utf-8"))

facet_counts = {
    facet.get("property"): {
        value.get("val"): value.get("count")
        for value in facet.get("values", [])
    }
    for facet in facets.get("facets", [])
}

print("QUALITY_GATE=" + quality_gate.get("projectStatus", {}).get("status", "UNKNOWN"))
print("ISSUES_TOTAL=" + str(issues.get("total", 0)))
for severity, count in sorted(facet_counts.get("severities", {}).items()):
    print(f"ISSUES_SEVERITY_{severity}={count}")
for issue_type, count in sorted(facet_counts.get("types", {}).items()):
    print(f"ISSUES_TYPE_{issue_type}={count}")

for item in issues.get("issues", [])[:20]:
    location = item.get("component", "")
    if item.get("line"):
        location += ":" + str(item["line"])
    message = item.get("message", "").replace("\n", " ")
    print(f"- {item.get('severity', 'UNKNOWN')} {item.get('type', 'UNKNOWN')} {location} {message}")
PY
```

If the total issue count exceeds the page size and every raw issue is needed, paginate with `p` and `ps`:

```bash
mkdir -p "$SONAR_OUTPUT_DIR/issues-pages"
page=1
while :; do
  file="$SONAR_OUTPUT_DIR/issues-pages/issues-$page.json"
  curl -fsS -u "$TOKEN:" --get \
    --data-urlencode "componentKeys=$SONAR_PROJECT_KEY" \
    --data-urlencode "resolved=false" \
    --data-urlencode "p=$page" \
    --data-urlencode "ps=500" \
    "$SONAR_URL/api/issues/search" \
    > "$file"
  count="$(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))["issues"]))' "$file")"
  [ "$count" -eq 0 ] && break
  page=$((page + 1))
done
```
