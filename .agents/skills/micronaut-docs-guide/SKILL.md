---
name: micronaut-docs-guide
description: Maintainer workflow for authoring and updating Micronaut Framework module guides in micronaut-projects repositories. Use when asked to "write docs", "add guide section", "update toc.yml", "fix docs build", "publish guide", or apply Micronaut Asciidoctor conventions such as dependency snippets and configuration property includes.
metadata:
  author: Álvaro Sánchez-Mariscal
---

# Write Micronaut Maintainer Documentation Guides

Use this skill to implement guide changes for Micronaut framework repositories generated from the Micronaut project template.

## Step 1: Confirm Repository Documentation Context

1. Read `src/main/docs/guide/toc.yml`.
2. List `src/main/docs/guide/**/*.adoc`.
3. Read `CONTRIBUTING.md` for docs build commands.
4. Confirm guide build entry points from repository conventions:
   - `./gradlew publishGuide` (or `./gradlew pG`) to assemble the guide.
   - `./gradlew docs` to build guide plus Javadocs.

If the repository layout diverges, follow local conventions and report the divergence.

## Step 2: Keep `toc.yml` and Files in Lockstep

Treat `src/main/docs/guide/toc.yml` as the source of truth for guide structure.

Rules:

1. Every visible guide section must exist in `toc.yml`.
2. Every referenced section key must map to a real `.adoc` file path.
3. Preserve existing section order unless the request explicitly changes navigation.
4. For nested sections, use YAML nesting under a parent key with `title`.

Nested pattern example:

```yaml
controlPanels:
  title: Available Control Panels
  builtIn: Built-in
  management: Management
```

This maps to:

- `src/main/docs/guide/controlPanels.adoc`
- `src/main/docs/guide/controlPanels/builtIn.adoc`
- `src/main/docs/guide/controlPanels/management.adoc`

## Step 3: Apply Micronaut Guide Authoring Conventions

Prefer project patterns used in `micronaut-projects/*` module guides.

Use this mapping:

| Need | Preferred pattern |
|---|---|
| Dependency instructions | `dependency:group:artifact[scope=...]` |
| Configuration properties table | `include::{includedir}configurationProperties/<fqcn>.adoc[]` |
| Config snippets | `[configuration]` + source block |
| Shell commands | `[source,bash]` blocks |
| Images | `image::<filename>[]` with assets in `src/main/docs/resources/img/` |
| Repository/release links | `https://github.com/{githubSlug}` patterns |

Guardrails:

1. Do not hardcode separate Maven/Gradle snippets when `dependency:` macro is appropriate.
2. Keep environment-sensitive instructions explicit (for example `MICRONAUT_ENVIRONMENTS=dev`).
3. Prefer stable links to official Micronaut docs for endpoint behavior.

Read `${CLAUDE_SKILL_ROOT}/references/control-panel-patterns.md` for concrete examples.

## Step 4: Use Micronaut Docs-Provided Generation Correctly

Read `${CLAUDE_SKILL_ROOT}/references/micronaut-docs-providers.md` before editing generated configuration docs references.

Key behavior to preserve:

1. `io.micronaut.documentation.asciidoc.AsciiDocPropertyReferenceWriter` generates AsciiDoc configuration property references from Micronaut metadata.
2. Generated output is consumed through includes under `{includedir}configurationProperties/`.
3. Documentation should include generated property docs rather than manually duplicating property tables.

## Step 5: Build and Validate Documentation

Run validation from repository root:

```bash
./gradlew publishGuide
./gradlew docs
```

Validation checklist:

1. Commands exit with code `0`.
2. Guide output exists under `build/docs/`.
3. New/updated sections appear in navigation and render without missing includes.
4. New images resolve and links are valid.

If `publishGuide` succeeds but `docs` fails, fix the failing stage and re-run both commands.

## Step 6: Maintainer-Focused Delivery Contract

When finishing a docs task, report:

1. Exact files changed (`.adoc`, `toc.yml`, docs resources).
2. Which conventions were applied (`dependency:`, config includes, `[configuration]`).
3. Build commands run and outcomes.
4. Any unresolved repo-specific divergences or follow-up actions.
