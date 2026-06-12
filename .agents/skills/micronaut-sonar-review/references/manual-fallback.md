# Manual Fallback

Use this when a repository needs one-off Gradle behavior that should not be baked into the helper.

## Start SonarQube Only

Bootstrap a local SonarQube container, token, automatic port, and `run.env` without running Gradle:

```bash
SONAR_RUN_ID="sourcegen-$(date +%s)-$$"
SONAR_OUTPUT_DIR="build/sonar-local/${SONAR_RUN_ID}"

SONAR_SKIP_GRADLE=true \
SONAR_IMAGE=sonarqube:community \
SONAR_OUTPUT_DIR="$SONAR_OUTPUT_DIR" \
SONAR_RUN_ID="$SONAR_RUN_ID" \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-local.sh
```

Load the generated values:

```bash
. "$SONAR_OUTPUT_DIR/run.env"
TOKEN="$(cat "$SONAR_TOKEN_FILE")"
```

Do not hard-code a host port. Use `SONAR_URL` from `run.env`.

## Run Gradle Manually

Example for `micronaut-sourcegen`:

```bash
SONAR_USER_HOME="$SONAR_USER_HOME" \
SONAR_TOKEN="$TOKEN" \
./gradlew sonar --no-parallel --continue \
  -Dsonar.host.url="$SONAR_URL" \
  -Dsonar.token="$TOKEN" \
  -Dsonar.projectKey=micronaut-sourcegen \
  -Dsonar.userHome="$SONAR_USER_HOME" \
  -Dsonar.coverage.jacoco.xmlReportPaths= \
  -Dsonar.qualitygate.wait=true \
  -Dsonar.qualitygate.timeout=180 \
  > "$SONAR_OUTPUT_DIR/gradle-sonar.log" 2>&1
```

Then extract issues:

```bash
SONAR_RUN_ENV="$SONAR_OUTPUT_DIR/run.env" \
SONAR_TOKEN="$TOKEN" \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-extract-issues.sh
```

Prefer the helper's built-in argument hooks when they are enough:

```bash
SONAR_GRADLE_TASK=sonar \
SONAR_SCANNER_ARGS="-Dsonar.coverage.jacoco.xmlReportPaths=" \
~/.codex/skills/micronaut-sonar-review/scripts/micronaut-sonar-local.sh
```

The helper adds `--no-parallel --continue` to the Sonar Gradle invocation by default.
