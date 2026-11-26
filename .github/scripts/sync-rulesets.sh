#!/usr/bin/env bash
# Syncs the shared repository rulesets in .github/rulesets.json to one repository.
#
# Usage: sync-rulesets.sh <owner/repo> <rulesets.json> [--dry-run]
#
# Each entry has a "name", a "ruleset" in the body format of GitHub's repository rulesets API, and an optional
# "only_if" {"path", "contains"}: the ruleset is applied only when that file on the repository's default branch
# contains that text, for example a required check that only exists once the synced gradle.yml has been merged.
# A ruleset of the repository with the same name is updated when it differs, or created when there is none. When
# "only_if" does not hold, an existing ruleset of that name is left alone. Other rulesets and classic branch
# protection rules are not touched. Managing rulesets needs the repository's admin permission.
set -euo pipefail

repo=$1
rulesets_file=$2
dry_run=${3:-}

run() {
  if [ "$dry_run" = "--dry-run" ]; then
    printf 'would run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

# Comparable form of a ruleset: only the fields we manage, with arrays sorted, without the null fields GitHub may add
# to rules, and with the organisation admin actor id GitHub reports as null.
normalize='{target, enforcement, conditions,
  bypass_actors: ((.bypass_actors // []) | map(if .actor_type == "OrganizationAdmin" then .actor_id = null else . end)
    | sort_by(.actor_type, .actor_id)),
  rules: ((.rules // []) | map(with_entries(select(.value != null))) | sort_by(.type))}'

default_branch=$(gh api "repos/$repo" --jq .default_branch)
existing=$(gh api "repos/$repo/rulesets?includes_parents=false&per_page=100" \
  --jq '.[] | select(.source_type == "Repository") | [.name, (.id|tostring)] | @tsv')

count=$(jq 'length' "$rulesets_file")
for ((i = 0; i < count; i++)); do
  entry=$(jq -c ".[$i]" "$rulesets_file")
  name=$(jq -r '.name' <<<"$entry")
  body=$(jq -c '.ruleset + {name: .name}' <<<"$entry")

  only_path=$(jq -r '.only_if.path // empty' <<<"$entry")
  if [ -n "$only_path" ]; then
    only_text=$(jq -r '.only_if.contains' <<<"$entry")
    content=$(gh api "repos/$repo/contents/$only_path?ref=$default_branch" --jq .content 2>/dev/null | base64 -d 2>/dev/null || true)
    if ! grep -qF -- "$only_text" <<<"$content"; then
      echo "Skipping '$name': $only_path on $default_branch does not contain '$only_text' yet"
      continue
    fi
  fi

  id=$(awk -F '\t' -v n="$name" '$1 == n { print $2; exit }' <<<"$existing")
  if [ -z "$id" ]; then
    echo "Creating ruleset '$name'"
    run gh api -X POST "repos/$repo/rulesets" --input - --silent <<<"$body"
  else
    current=$(gh api "repos/$repo/rulesets/$id" | jq -S "$normalize")
    wanted=$(jq -S "$normalize" <<<"$body")
    if [ "$current" = "$wanted" ]; then
      echo "Ruleset '$name' is up to date"
    else
      echo "Updating ruleset '$name'"
      run gh api -X PUT "repos/$repo/rulesets/$id" --input - --silent <<<"$body"
    fi
  fi
done
