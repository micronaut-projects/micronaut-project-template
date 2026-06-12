---
name: micronaut-sonar-review
description: Start or reuse a local SonarQube server in Docker, run the Micronaut Gradle sonar task against it, extract Sonar issues and quality-gate status, and validate the review results. Use when Codex is asked to run local Sonar, SonarQube, sonar review, Micronaut sonar analysis, validate a Sonar report, or inspect Sonar issues for a Micronaut repository.
---

# Micronaut Sonar Review

## Overview

Use this skill to run a repeatable local SonarQube review for Micronaut projects. Prefer the bundled `scripts/micronaut-sonar-local.sh` helper instead of retyping Docker, Gradle, and Web API calls.

The `.sh` entrypoints are thin wrappers around Python scripts. Keep shared logic in Python so the workflow behaves consistently on macOS and Linux.

## Workflow

1. Confirm Docker is available:

   ```bash
   docker info
   ```

2. For change-specific review, always ask or confirm which revision the Sonar
   checks should be compared against before running analysis. First use Git to
   suggest a likely base, such as the current branch upstream, the PR base, or
   the remote default branch. If no likely base is clear, show the remote branch
   list once and ask the user to choose. The revision may be a remote branch,
   tag, commit SHA, or PR base. If the user already provided the revision,
   repeat it back in the run notes; otherwise ask before judging Sonar issues.

3. Resolve the comparison revision with Git before running Sonar. Fetch the
   relevant remote branch when needed, verify the revision resolves to a commit,
   and record the resolved commit SHA.

4. Run Sonar on the comparison revision first and extract its results. Use a
   temporary `git worktree` for the comparison revision so the current working
   tree, including uncommitted changes, is not disturbed. Keep the baseline
   output directory and `run.env`. When the baseline worktree is under
   `${TMPDIR:-/tmp}`, keep the baseline `SONAR_OUTPUT_DIR` under `${TMPDIR:-/tmp}`
   too; writing baseline output back into the original repository from the
   temporary worktree can require extra filesystem permissions.

5. Return to the current version, run Sonar again, and extract its results into
   a separate output directory.

6. From the repository root or comparison worktree root, run each Sonar analysis with:

   ```bash
   ~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-local.sh
   ```

7. The helper runs the Sonar Gradle task with `--no-parallel --continue` by
   default. Pass repository-specific scanner flags through environment variables:

   ```bash
   SONAR_GRADLE_TASK=sonar \
   SONAR_SCANNER_ARGS="-Dsonar.coverage.jacoco.xmlReportPaths=" \
   ~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-local.sh
   ```

8. Review generated artifacts under each `build/sonar-local/<run-id>/`:
   - `run.env`: resolved `SONAR_URL`, automatic port, output directory, container name, and token file path when available
   - `gradle-sonar.log`: Gradle analysis log
   - `summary.txt`: compact human-readable review summary
   - `quality-gate.json`: quality-gate status from `/api/qualitygates/project_status`
   - `issues.json`, `issues-all.json`, `issues-pages/`, `issues-facets.json`, `issues-high.json`, `issues-bugs.json`
   - `measures.json`: project measures where available

9. Compare the comparison-revision results with the current-version results
   before reporting. Use the bundled comparator:

   ```bash
   SONAR_BASELINE_DIR=build/sonar-local/<baseline-run-id> \
   SONAR_CURRENT_DIR=build/sonar-local/<current-run-id> \
   ~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-compare-issues.sh
   ```

   State the comparison revision, both run IDs/output directories, quality-gate
   changes, issue count deltas, bug count deltas, and new or changed high-value
   Sonar issues. Always write newly introduced issues as groups before listing
   individual locations.

10. Validate the review before reporting results:
   - Confirm both `summary.txt` files include the project key, quality-gate status, and issue counts.
   - Treat `QUALITY_GATE=OK` as passing only when the relevant script completed successfully.
   - If issues are present, inspect severity, type, component, line, and message before recommending fixes.
   - For change-specific review, state the comparison revision used and separate newly introduced/current-version Sonar findings from existing project-wide findings.
   - Present newly introduced issues in groups and ask the user whether any groups should be fixed before making code changes.
   - If either Gradle task failed but Sonar produced partial results, report both the Gradle failure and the extracted Sonar state.

## Issue Extraction

The local helper runs extraction automatically after Gradle analysis. To extract from an existing uploaded analysis, use the run-specific environment file:

```bash
SONAR_RUN_ENV=build/sonar-local/<run-id>/run.env \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-extract-issues.sh
```

If `SONAR_RUN_ENV` and `SONAR_OUTPUT_DIR` are omitted, the extractor tries the latest `build/sonar-local/*/run.env`. For parallel reviews, always pass the intended `SONAR_RUN_ENV`.

Detailed API extraction notes and manual curl equivalents live in `references/issue-extraction.md`.

## Issue Comparison

After baseline and current runs are extracted, compare them with:

```bash
SONAR_BASELINE_DIR=build/sonar-local/<baseline-run-id> \
SONAR_CURRENT_DIR=build/sonar-local/<current-run-id> \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-compare-issues.sh
```

The comparator writes `compare.json` and `compare-summary.txt` under
`$SONAR_CURRENT_DIR/sonar-compare/` by default. Override with
`SONAR_COMPARE_OUTPUT_DIR` or `--output`.

`compare-summary.txt` always includes grouped newly introduced issue sections:

- `NEW_BUG_GROUPS`
- `NEW_HIGH_GROUPS`
- `NEW_ISSUE_GROUPS`

Groups are keyed by Sonar type, severity, rule, and normalized message, with
the affected locations listed under each group. When reporting comparison
results, copy the relevant groups into the response and ask whether the user
wants any or all groups fixed. Do not start fixing grouped findings until the
user confirms the requested group or scope.

Useful overrides:

```bash
SONAR_COMPARE_IDENTITY=auto
SONAR_COMPARE_TOP=30
```

`SONAR_COMPARE_IDENTITY=auto` uses Sonar issue keys when the two runs share
keys, otherwise it falls back to a stable issue fingerprint. Use
`SONAR_COMPARE_IDENTITY=key` only when both runs come from the same SonarQube
project history; use `SONAR_COMPARE_IDENTITY=fingerprint` for independent local
runs.

## Revision Comparison

When the user wants a Sonar review of current changes, compare against an explicit revision before drawing conclusions:

1. Ask or confirm the comparison revision first. Suggest the likely Git base
   branch when one is clear; otherwise show remote branches once and ask the
   user to choose.
2. Resolve and record the comparison commit with Git.
3. Run Sonar on that revision first and extract results before running Sonar on the current version.
4. Run Sonar on the current version second and extract results to a different output directory.
5. Compare `summary.txt`, `quality-gate.json`, `issues-facets.json`, `issues-all.json`, `issues-high.json`, and `issues-bugs.json` from both runs.
6. Prefer `scripts/micronaut-sonar-compare-issues.sh` for this comparison.
7. Prioritize newly introduced or worsened Sonar issues, with special attention to `BUG`, `BLOCKER`, and `CRITICAL` issues.
8. Report newly introduced/current-version Sonar findings as groups, separate them from pre-existing project-wide Sonar findings, name the comparison revision used, and ask which groups should be fixed.

Compare Sonar issues by extracted issue identity, not by Git diff ranges. Prefer
Sonar `key` when both runs came from the same SonarQube project history. When
runs used separate local SonarQube instances, compare a stable fingerprint such
as `component`, `line`, `rule`, `type`, `severity`, and normalized `message`.
Use `issues-bugs.json` for the bug-specific delta and `issues-high.json` for
high-severity deltas.

## Git Interaction

Use Git only for revision selection and baseline worktree setup, not for deciding
which Sonar issues matter. The comparison is between the extracted Sonar issue
sets from the baseline revision and the current version.

```bash
git status --short
git branch --show-current
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git branch -r --format='%(refname:short)'
git fetch <remote> <branch>
git rev-parse --verify '<comparison-revision>^{commit}'
```

Use the upstream branch, PR base, or remote default branch as the suggested
comparison revision when that choice is clear. When it is not clear, show
`git branch -r --format='%(refname:short)'` once and ask the user which revision
to use. Only fetch the remote needed for the comparison revision. If the
revision is already present locally, `git fetch` is optional. If the current
worktree has uncommitted changes, do not checkout the comparison revision in
place.

Create a temporary baseline worktree for the comparison run:

```bash
BASE_SHA="$(git rev-parse --verify '<comparison-revision>^{commit}')"
BASE_ROOT="${TMPDIR:-/tmp}/micronaut-sonar-baseline-${BASE_SHA}"
BASE_WORKTREE="$BASE_ROOT/worktree"
BASE_SONAR_OUTPUT="$BASE_ROOT/sonar-output"
git worktree add --detach "$BASE_WORKTREE" "$BASE_SHA"
```

Run the baseline Sonar analysis inside `$BASE_WORKTREE` first with
`SONAR_OUTPUT_DIR="$BASE_SONAR_OUTPUT"`. Then run the current Sonar analysis in
the original worktree with a separate output directory. The comparator accepts
absolute paths, so the baseline output can stay in tmp:

```bash
SONAR_BASELINE_DIR="$BASE_SONAR_OUTPUT" \
SONAR_CURRENT_DIR=build/sonar-local/<current-run-id> \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-compare-issues.sh
```

Remove the temporary worktree only after preserving the baseline `run.env`,
`summary.txt`, and extracted issue files needed for comparison.

## Defaults

The helper uses these defaults:

```bash
SONAR_IMAGE=sonarqube:community
SONAR_RUN_ID=<timestamp-pid-random>
SONAR_CONTAINER=codex-sonarqube-<repo-name>-<run-id>
SONAR_PORT=<auto-assigned Docker host port>
SONAR_URL=http://127.0.0.1:<auto-assigned-port>
SONAR_PROJECT_KEY=<repo-directory-name>
SONAR_GRADLE_TASK=auto
SONAR_GRADLE_ARGS="--no-parallel --continue"
SONAR_SCANNER_ARGS=
SONAR_OUTPUT_DIR=build/sonar-local/<run-id>
SONAR_STATE_DIR=build/sonar-local/<run-id>/state
SONAR_USER_HOME=build/sonar-local/<run-id>/sonar-user-home
```

Override defaults with environment variables. By default each run gets a unique container name, output directory, state directory, scanner cache directory, and Docker-assigned host port so multiple reviews can run in parallel. Set `SONAR_PORT` only when a fixed port is required. Do not assume SonarQube is on port `9000`; read the run's `run.env`.

Set `SONAR_GRADLE_ARGS=` only when the repository explicitly requires disabling the default `--no-parallel --continue` flags.

Use `SONAR_TOKEN` and `SONAR_URL` when targeting an existing secured SonarQube instance. For a local Docker container, the helper logs in with the default `admin/admin` account on first use, changes it to a generated temporary password when supported, and stores the local password/token under `SONAR_STATE_DIR`.

Set `SONAR_SKIP_GRADLE=true` to start or reuse SonarQube, bootstrap credentials, and write `run.env` without running Gradle. Use this for one-off manual analysis flows; see `references/manual-fallback.md`.

## Micronaut Conventions

Follow repository Gradle instructions:

- Run Gradle through `./gradlew`.
- Keep non-test Gradle commands quiet where practical, but do not hide the Sonar task log; the helper captures it to `gradle-sonar.log`.
- The local Sonar Gradle invocation should include `--no-parallel --continue`; the helper applies those flags by default.
- If the repository CI runs Sonar with extra scanner flags, mirror them locally through `SONAR_SCANNER_ARGS`.
- Do not commit generated Sonar output.
- Do not modify build logic just to make Sonar run unless the user explicitly asks for build changes.

## Findings And Troubleshooting

- Some Micronaut builds expose the root `sonar` task only when `SONAR_TOKEN` exists. The helper now starts SonarQube and bootstraps a token before auto-detecting the Gradle task. If auto-detection still fails, set `SONAR_GRADLE_TASK=sonar` explicitly.
- `sonarqube:lts-community` can be too old for repositories compiled with newer Java releases. For Java 25 class files, the LTS analyzer failed with `java.lang.IllegalArgumentException: 25`; the helper defaults to `sonarqube:community`.
- `--no-parallel --continue` avoids Gradle unsafe configuration resolution failures seen under Gradle 9 during Sonar analysis.
- The helper sets `SONAR_USER_HOME` and `-Dsonar.userHome` under the run output directory so scanner cache writes stay inside the workspace.
- If JaCoCo import fails with `Premature end of file` for `build/reports/jacoco/testCodeCoverageReport/testCodeCoverageReport.xml`, regenerate a valid coverage report or disable coverage import for the local review with `SONAR_SCANNER_ARGS="-Dsonar.coverage.jacoco.xmlReportPaths="`.
- If Docker cannot start SonarQube, verify Docker is running. Ports are assigned automatically unless `SONAR_PORT` is set explicitly.
- If a reused local container cannot authenticate, reuse the same `SONAR_STATE_DIR`, set `SONAR_TOKEN`, or recreate the local SonarQube container.
- If quality-gate polling times out, inspect `gradle-sonar.log` and `quality-gate.json`; SonarQube may still be computing the background task.

## References

- `references/issue-extraction.md`: extractor outputs, environment overrides, and manual Sonar Web API commands.
- `references/manual-fallback.md`: server bootstrap without Gradle, manual Gradle invocation, and extraction from `run.env`.
