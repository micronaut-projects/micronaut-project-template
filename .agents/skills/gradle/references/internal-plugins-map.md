# Internal Plugin Map (micronaut-build Source)

Use this map when deciding where a Gradle change belongs.

## Entry Points

- `io.micronaut.build.shared.settings` (`MicronautSharedSettingsPlugin`)
  - Applies settings extension plugin and Develocity plugin.
  - Configures standardized project names (`micronaut-` prefix) when enabled.
  - Sets project `version`/`group` from properties during project loading.
  - Provides publishing repository wiring and optional Nexus setup.
  - Writes `micronaut-build-version` into `buildSrc/gradle.properties`.

- `io.micronaut.build.internal.parent` (`MicronautParentPlugin`)
  - Root-only orchestration plugin.
  - Applies docs, quality-reporting, and parent-publishing plugins.

## Project-Level Build Extension

- `MicronautBuildExtensionPlugin`
  - Creates project extension `micronautBuild`.
  - Defaults test framework to `SPOCK`.
  - Configures `useToolchains` from environment.

- `MicronautBuildExtension`
  - Key properties include:
    - `javaVersion`
    - `testJavaVersion`
    - `enableProcessing`
    - `enableBom`
    - `testFramework`
    - `useToolchains`

## Module and Common Plugins

- `io.micronaut.build.internal.base` (`MicronautBasePlugin`)
  - Applies dependency-resolution config and build extension plugin.
  - Validates project version format.
  - Applies additional base support plugins.

- `io.micronaut.build.internal.base-module` (`MicronautBaseModulePlugin`)
  - Applies common build, dependency updates, publishing, binary compatibility, module info.
  - Enforces settings plugin internal state checks.

- `io.micronaut.build.internal.module` (`MicronautModulePlugin`)
  - Applies base-module plugin.
  - Adds standard Micronaut module dependencies.
  - Configures test dependencies according to `micronautBuild.testFramework`.

- `io.micronaut.build.internal.common` (`MicronautBuildCommonPlugin`)
  - Applies Java/Groovy defaults and quality participant plugin.
  - Wires BOM usage through `globalBoms` and version providers.
  - Configures compile options, idea, spotless, and test logger behavior.

## BOM and Publishing

- `io.micronaut.build.internal.bom` (`MicronautBomPlugin`)
  - Configures Java Platform + Version Catalog publication.
  - Creates helper configurations for BOM and catalog inlining.
  - Supports managed dependencies and BOM/catalog inlining controls.

- `io.micronaut.build.internal.publishing` (`MicronautPublishingPlugin`)
  - Applies Maven Publish and configures publication metadata from gradle properties.
  - Maps module artifact id using `moduleNameOf` (`micronaut-` prefix rule).
  - Embeds generated POM into output jars and wires signing conditions.

## Settings Extension Highlights

- `MicronautBuildSettingsExtension` adds:
  - `importMicronautCatalog()` and `importMicronautCatalog(alias)`
  - `requiresDevelopmentVersion(githubProjectName, branch)`
  - standardized naming controls and cache toggles

## Control Panel Usage Example

- In `settings.gradle.kts`:
  - Applies `io.micronaut.build.shared.settings`
  - Enables `useStandardizedProjectNames`
  - Imports `mn` and additional `mn*` catalogs
- In root `build.gradle.kts`:
  - Applies `io.micronaut.build.internal.parent`
- In `buildSrc` convention plugin:
  - Wraps `io.micronaut.build.internal.module`

This pattern is the canonical maintainer path for module repositories generated from the template.
