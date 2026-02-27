---
name: gradle
description: Maintainer workflow for Gradle changes in micronaut-projects repositories. Use when asked to update Micronaut module build logic, apply io.micronaut.build internal plugins, debug module naming with micronaut- prefixes, or align repository builds with current Gradle major-version best practices.
metadata:
  author: Álvaro Sánchez-Mariscal
  gradle-major-version: "9.x"
---

# Maintain Gradle in Micronaut Framework Repositories

Use this skill to make safe, source-grounded Gradle changes in `micronaut-projects/*` repositories intended for framework maintainers.

Coverage target: this skill currently covers repositories on Gradle major version `9.x`.

## Step 1: Confirm Repository Context and Build Entry Points

1. Read `settings.gradle` or `settings.gradle.kts` first.
2. Confirm the settings plugin is applied:
   - `io.micronaut.build.shared.settings`
3. Read root `build.gradle` or `build.gradle.kts`.
4. Confirm the root plugin is applied:
   - `io.micronaut.build.internal.parent`
5. Read `buildSrc/` convention plugins before changing module build files.
6. Confirm repository intent from `gradle.properties` metadata (`projectDesc`, `projectUrl`, `githubSlug`) when changes affect publishing/docs.

Repository shape guardrails:

- Treat the root project as a parent/coordination project; avoid adding production source code there.

If those plugins are missing, treat the repository as customized and map the local convention plugins before editing.

## Step 2: Resolve Directory Name vs Gradle Module Name

Always treat project directory names and Gradle module names as different concerns.

| Directory | Included project | Standardized module name |
|---|---|---|
| `control-panel-core` | `include("control-panel-core")` | `:micronaut-control-panel-core` |
| `control-panel-ui` | `include("control-panel-ui")` | `:micronaut-control-panel-ui` |

Apply this rule:

1. Check `micronautBuild.useStandardizedProjectNames` in settings.
2. If enabled, module names are prefixed with `micronaut-` by build logic.
3. Use the prefixed module path in Gradle task targeting and project dependencies.
4. If unsure about actual module paths in a repository, run:

```bash
./gradlew projects
```

Also enforce naming categories used by Micronaut module repos:

- Published modules: `micronaut-*`
- Test suites: `test-suite-*`
- Documentation examples: `doc-examples-*`

Example task targeting:

```bash
./gradlew :micronaut-control-panel-core:test
```

## Step 3: Map Internal Plugin Responsibilities Before Editing

Read `${CLAUDE_SKILL_ROOT}/references/internal-plugins-map.md` and map your target change to the plugin that owns it.

Use this decision table:

| Need | Primary plugin |
|---|---|
| Settings-level catalogs, naming, cache toggles, included builds | `io.micronaut.build.shared.settings` |
| Root aggregation of docs/quality/publishing | `io.micronaut.build.internal.parent` |
| Standard library module defaults | `io.micronaut.build.internal.module` |
| BOM project behavior and catalog inlining | `io.micronaut.build.internal.bom` |
| Publishing/signing/POM metadata | `io.micronaut.build.internal.publishing` |

Prefer changing the convention plugin layer (`buildSrc`) over repeating logic in module `build.gradle(.kts)` files.

## Step 4: Apply Current Gradle Major-Version Practices

Read `${CLAUDE_SKILL_ROOT}/references/gradle-current-major-best-practices.md` and apply the relevant items.

Mandatory defaults for new changes:

1. Use lazy configuration APIs (`Provider`, `Property`, `configureEach`, `tasks.register`).
2. Keep configuration cache compatibility; do not introduce eager cross-project access.
3. Keep dependency versions centralized in version catalogs; avoid inline versions in module scripts.
4. Use convention plugins for shared behavior, not root `subprojects {}` or duplicated per-module blocks.
5. Use Java toolchains consistently when configured by repository conventions.

## Step 5: Implement in the Right Layer

Choose one layer and keep the change localized:

1. `settings.gradle(.kts)` for settings extension concerns (`importMicronautCatalog`, standardized names, development includes).
2. Root build for parent orchestration concerns only.
3. `buildSrc` convention plugin for shared module behavior.
4. Module `build.gradle(.kts)` only for module-specific dependencies or narrowly scoped flags.
5. Prefer Kotlin DSL (`build.gradle.kts`) for new modules.

Do not duplicate behavior already provided by `io.micronaut.build.internal.*` plugins.

## Step 6: Validate Like a Maintainer

Run the smallest valid verification set first, then broaden.

1. Compile affected modules first (for example `:<module>:compileTestJava`, and `compileTestGroovy` when present).
2. Run Checkstyle early to fail fast (for example `:<module>:checkstyleMain`, or repository aggregate aliases such as `cM` when available).
3. Run targeted tests for fast feedback (for example `:<module>:test --tests 'pkg.ClassTest'`).
4. Run full tests for affected modules (`:<module>:test`).
5. Run repository checks expected by that module (quality/doc gates such as `check docs`).
6. Full build only when needed.

Before considering the task complete, run the required repository-level checks:

```bash
./gradlew check docs
```

For style failures, address Checkstyle first, then run formatter fixes and re-check:

```bash
./gradlew spotlessApply spotlessCheck
```

For public API-affecting changes, verify binary compatibility:

```bash
./gradlew japiCmp
```

When adding a new module, ensure binary compatibility checks are configured in that module, for example:

```kotlin
micronautBuild {
    binaryCompatibility.enabledAfter("2.0.0")
}
```

If `japiCmp` fails because of intentional internal-only evolution, update the accepted API changes metadata according to repository conventions.

Before finalizing, verify the working tree contains only intended changes.

Use the wrapper from repository root:

```bash
./gradlew <tasks>
```

When reporting results, include:

1. Which module paths were used (prefixed names).
2. Which convention plugin or settings entry point was changed.
3. Which checks passed or failed.
4. For docs changes, confirm output generated under `build/docs/`.

For documentation-related Gradle changes, verify the docs conventions are respected:

1. Use `dependency:` macro for dependency snippets (avoid hardcoded Gradle/Maven blocks).
2. Use `snippet:` includes for code snippets.
3. Use `[configuration]` macro for configuration snippets.

## Step 7: Output Contract for Maintainer Requests

When finishing, provide:

1. Exact files changed.
2. The internal plugin boundary respected.
3. The module naming interpretation used (`directory` -> `:micronaut-*`).
4. Verification commands and outcomes.

If repository behavior diverges from this skill, report the divergence and follow local repository conventions.
