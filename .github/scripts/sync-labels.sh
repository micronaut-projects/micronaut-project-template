#!/usr/bin/env bash
# Syncs the shared labels in .github/labels.json to one repository.
#
# Usage: sync-labels.sh <owner/repo> <labels.json> [--dry-run]
#
# For each shared label, every alias found in the repository is merged into it first:
# - if the shared label does not exist yet, the alias is renamed, which keeps it on its issues and pull requests;
# - otherwise the shared label is added to each issue and pull request that has the alias, then the alias is deleted.
# Then each shared label is created, or its colour and description are updated.
# Labels that are neither shared nor an alias are left alone.
set -euo pipefail

repo=$1
labels_file=$2
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

# Label names are case-insensitive on GitHub: compare in lower case, act on the repo's spelling.
existing=$(gh api --paginate "repos/$repo/labels?per_page=100" --jq '.[].name')
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
    for number in $(gh api --paginate "repos/$repo/issues?labels=$encoded&state=all&per_page=100" --jq '.[].number'); do
      run gh api -X POST "repos/$repo/issues/$number/labels" -f "labels[]=$name" --silent
      # Stay under GitHub's secondary rate limit for writes; a run cut short resumes the next night.
      [ "$dry_run" = "--dry-run" ] || sleep 1
    done
    run gh label delete "$actual_alias" --repo "$repo" --yes
  fi
done < <(jq -r '.[] | .name as $n | (.aliases // [])[] | [$n, .] | @tsv' "$labels_file")

jq -r '.[] | [.name, .color, .description] | @tsv' "$labels_file" |
  while IFS=$'\t' read -r name color description; do
    run gh label create "$name" --repo "$repo" --color "$color" --description "$description" --force
  done
