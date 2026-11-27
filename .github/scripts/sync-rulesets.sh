#!/usr/bin/env bash
# Syncs the shared repository rulesets in .github/rulesets.json to one repository.
#
# Usage: sync-rulesets.sh <owner/repo> <rulesets.json> [--prune] [--dry-run]
#
# Each entry has a "name", a "ruleset" in the body format of GitHub's repository rulesets API, and an optional
# "only_if" {"path", "contains"}: the ruleset is applied only when that file on the repository's default branch
# contains that text, for example a required check that only exists once the synced gradle.yml has been merged.
# A ruleset of the repository with the same name is updated when it differs, or created when there is none. When
# "only_if" does not hold, an existing ruleset of that name is left alone.
#
# With --prune, the shared rulesets are the only branch rules of the repository: afterwards every other repository
# ruleset and every classic branch protection rule is deleted. Without it, they are not touched. Managing rulesets and
# branch protection needs the repository's admin permission.
set -euo pipefail

repo=$1
rulesets_file=$2
shift 2
dry_run=
prune=
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=--dry-run ;;
    --prune) prune=--prune ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

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

if [ "$prune" != "--prune" ]; then
  exit 0
fi

# Rulesets of the repository itself (not inherited) whose name is not one of the shared ones.
while IFS=$'\t' read -r name id; do
  [ -n "$id" ] || continue
  if ! jq -e --arg n "$name" 'any(.[]; .name == $n)' "$rulesets_file" >/dev/null; then
    echo "Deleting ruleset '$name'"
    run gh api -X DELETE "repos/$repo/rulesets/$id" --silent
  fi
done <<<"$existing"

# Classic branch protection rules, read through GraphQL so that patterns matching no branch are found too.
owner=${repo%%/*}
name=${repo#*/}
protection_rules=$(gh api graphql -f owner="$owner" -f name="$name" -f query='
  query($owner: String!, $name: String!) {
    repository(owner: $owner, name: $name) {
      branchProtectionRules(first: 100) { nodes { id pattern } }
    }
  }' --jq '.data.repository.branchProtectionRules.nodes[] | [.pattern, .id] | @tsv')
while IFS=$'\t' read -r pattern id; do
  [ -n "$id" ] || continue
  echo "Deleting classic branch protection '$pattern'"
  run gh api graphql -f id="$id" -f query='
    mutation($id: ID!) { deleteBranchProtectionRule(input: {branchProtectionRuleId: $id}) { clientMutationId } }' --silent
done <<<"$protection_rules"
