# Current Gradle Major-Version Best Practices for Micronaut Maintainers

Apply these when changing Gradle logic in multi-module Micronaut framework repositories.

Current coverage for this skill: Gradle major version `9.x`.

## Version Scope Policy

1. Treat the active Gradle major line as the source of truth.
2. Derive it from `gradle/wrapper/gradle-wrapper.properties`.
3. Do not hardcode patch-level guidance in maintainers docs.
4. Use `docs.gradle.org/current` pages for baseline recommendations.

## Build Performance and Correctness

1. Keep configuration cache compatible.
   - Use lazy APIs (`Provider`, `Property`, `configureEach`, `register`).
   - Avoid eagerly reading values at configuration time when not required.

2. Keep build logic in convention plugins.
   - Prefer `buildSrc`/precompiled convention plugins for shared rules.
   - Avoid repeating logic in many module build scripts.

3. Favor isolated, per-project logic.
   - Avoid global cross-project mutation patterns where possible.
   - Keep behavior composable and local to convention plugins.

## Dependency and Version Management

1. Keep versions centralized in version catalogs.
   - Avoid hardcoding dependency versions in module build files.

2. Use `java-library` API/implementation boundaries for reusable modules.
   - Keep API surface minimal for downstream compile classpaths.

3. Use platform/BOM alignment intentionally.
   - Keep managed coordinates in BOM/catalog and avoid drift.

## Task and Plugin Authoring Patterns

1. Register tasks lazily.
   - Prefer `tasks.register`/`tasks.named` over eager task creation.

2. Model task inputs/outputs explicitly.
   - This improves caching, up-to-date checks, and reproducibility.

3. Use toolchains for Java version consistency where repository conventions support it.

## CI and Reproducibility

1. Use Gradle wrapper from repository root for all automation.
2. Keep cache settings explicit and environment-aware.
3. Keep scan/test retry behavior in shared plugins, not ad hoc per module.

## Practical Implications for micronaut-projects

1. Do not bypass `io.micronaut.build.*` conventions unless necessary.
2. Make changes at the owning layer (settings/root/buildSrc/module).
3. Validate with targeted module tasks first, then broader checks.

## Sources

- https://docs.gradle.org/current/userguide/configuration_cache.html
- https://docs.gradle.org/current/userguide/lazy_configuration.html
- https://docs.gradle.org/current/userguide/best_practices_dependencies.html
- https://docs.gradle.org/current/userguide/structuring_software_projects.html
- https://docs.gradle.org/current/userguide/authoring_maintainable_builds.html
- https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
