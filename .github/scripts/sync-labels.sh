#!/usr/bin/env bash
# Syncs the shared labels in .github/labels.json to one repository.
#
# Usage: sync-labels.sh <owner/repo> <labels.json> [--dry-run]
#
# For each shared label, every alias found in the repository is merged into it first:
# - if the shared label does not exist yet, the alias is renamed, which keeps it on its issues and pull requests;
# - otherwise the shared label is added to each issue and pull request that has the alias, then the alias is deleted.
# Then each shared label is created, or its colour and description are updated when they differ.
# Labels that are neither shared nor an alias are left alone.
set -euo pipefail

repo=$1
labels_file=$2
dry_run=${3:-}

# GitHub's API sometimes answers 500 or 502 to a request that would otherwise succeed. Retries each call three times,
# 15, 30 and 45 seconds apart, before giving up. A write whose failure hid a success fails on its retry instead, and
# the next nightly run finds the work done.
retry() {
  local attempt=1
  until "$@"; do
    if [ "$attempt" -ge 4 ]; then
      return 1
    fi
    echo "Retrying in $((15 * attempt))s: $*" >&2
    sleep $((15 * attempt))
    attempt=$((attempt + 1))
  done
}

# Prints a read's whole output only once it succeeded, so a page that failed half way is never used.
read_retry() {
  local output attempt=1
  until output=$("$@"); do
    if [ "$attempt" -ge 4 ]; then
      return 1
    fi
    echo "Retrying in $((15 * attempt))s: $*" >&2
    sleep $((15 * attempt))
    attempt=$((attempt + 1))
  done
  printf '%s\n' "$output"
}

run() {
  if [ "$dry_run" = "--dry-run" ]; then
    printf 'would run:'
    printf ' %q' "$@"
    printf '\n'
  else
    retry "$@"
  fi
}

# Label names are case-insensitive on GitHub: compare in lower case, act on the repo's spelling.
# One line per label: name, colour and description, so that unchanged labels need no write.
current=$(read_retry gh api --paginate "repos/$repo/labels?per_page=100" --jq '.[] | [.name, .color, (.description // "")] | @tsv')
existing=$(cut -f1 <<<"$current")
find_label() {
  local wanted label
  wanted=$(tr '[:upper:]' '[:lower:]' <<<"$1")
  while IFS= read -r label; do
    if [ "$(tr "[:upper:]" "[:lower:]" <<<"$label")" = "$wanted" ]; then
      printf "%s" "$label"
      return 0
    fi
  done <<<"$existing"
  return 1
}

while IFS=$'\t' read -r name alias; do
  actual_alias=$(find_label "$alias") || continue
  if [ "$(tr '[:upper:]' '[:lower:]' <<<"$actual_alias")" = "$(tr '[:upper:]' '[:lower:]' <<<"$name")" ]; then
    continue
  fi
  if ! find_label "$name" >/dev/null; then
    echo "Renaming '$actual_alias' to '$name'"
    run gh label edit "$actual_alias" --repo "$repo" --name "$name"
    existing=$(printf '%s\n%s' "$existing" "$name")
  else
    echo "Merging '$actual_alias' into '$name'"
    encoded=$(jq -rn --arg l "$actual_alias" '$l|@uri')
    numbers=$(read_retry gh api --paginate "repos/$repo/issues?labels=$encoded&state=all&per_page=100" --jq '.[].number')
    for number in $numbers; do
      run gh api -X POST "repos/$repo/issues/$number/labels" -f "labels[]=$name" --silent
      # Stay under GitHub's secondary rate limit for writes; a run cut short resumes the next night.
      [ "$dry_run" = "--dry-run" ] || sleep 1
    done
    run gh label delete "$actual_alias" --repo "$repo" --yes
  fi
done < <(jq -r '.[] | .name as $n | (.aliases // [])[] | [$n, .] | @tsv' "$labels_file")

jq -r '.[] | [.name, .color, .description] | @tsv' "$labels_file" |
  while IFS=$'\t' read -r name color description; do
    if awk -F '\t' -v n="$name" -v c="$color" -v d="$description" \
      'tolower($1) == tolower(n) && $1 == n && tolower($2) == tolower(c) && $3 == d { found = 1 } END { exit !found }' \
      <<<"$current"; then
      continue
    fi
    run gh label create "$name" --repo "$repo" --color "$color" --description "$description" --force
  done
