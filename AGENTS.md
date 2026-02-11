# AGENTS.md (Micronaut Project Template)

This file provides **repository-local rules** for automated agents (OpenCode, GPT-5.2, Claude, etc.) working in Micronaut Projects repositories created from this template.

## 1) Build + verification rules (non-negotiable)

### 1.1 Published module naming and Gradle project paths

- **Published modules** Will be automatically prefixed with **`micronaut-`** meaning that when running Gradle commands they must include `micronaut-` otherwise the command will fail.
- **Test suites** MUST be prefixed with **`test-suite-`**.
- This template may still contain placeholder module names like `project-template`, but repositories created from it will be renamed to the `micronaut-...` / `test-suite-...` convention.

Correct (published module):

```bash
./gradlew micronaut-project-template:test
```

Incorrect (will not exist in repos created from this template):

```bash
./gradlew project-template:test
```

If you are unsure of module names, use `./gradlew projects` to find actual project names.

### 1.2 Always pass verifications

All changes MUST pass the full verification suite, including at least:

```bash
./gradlew check
./gradlew docs
```

This includes (but is not limited to) Checkstyle, Spotless, and documentation publishing.

### 1.3 Binary compatibility

- Public API must remain binary compatible unless the next versions is a new major version.
- Verify with:

```bash
./gradlew japiCmp
```

If adding a **new module**, enable binary compatibility checks starting from the next release, for example:

```groovy
micronautBuild {
    binaryCompatibility.enabledAfter("2.0.0")
}
```

If a japiCmp failure is caused by changes that are truly **internal-only**, update the accepted-changes JSON accordingly.

## 2) Gradle conventions

### 2.1 No hard-coded versions

- Never hard-code versions in Gradle build files.
- Define versions in **`gradle/libs.versions.toml`** and use type-safe references from build scripts.

### 2.2 Prefer Kotlin DSL for new modules

When adding new modules, prefer **`build.gradle.kts`** over Groovy for type safety.

### 2.3 Use Micronaut BOM imports via `importMicronautCatalog`

Import Micronaut catalogs in the `micronautBuild` block:

```groovy
micronautBuild {
    importMicronautCatalog()
    importMicronautCatalog("micronaut-validation")
}
```

With this convention:

- `io.micronaut:micronaut-core` is available as `mn.micronaut.core`
- `io.micronaut.validation:micronaut-validation` is available as `mnValidation.micronaut.validation`

Choose the correct dependency scope:

- `api` for dependencies that appear in public API/signatures
- `implementation` for internal implementation details
- `compileOnly` for compile-time only
- `runtimeOnly` for runtime only

## 3) Code rules

### 3.1 Nullability: JSpecify + @NullMarked

- All new code MUST use **JSpecify** nullability annotations.
- Packages should be **@NullMarked by default**.
- If a package has no `package-info.java`, create one.
- `@NonNull` should generally not be needed when using `@NullMarked`.

### 3.2 Formatting + style

- All new code must pass **Spotless** and **Checkstyle**.

### 3.3 Public API quality

- Any new public API must be **extensively documented** with Javadoc.
- Clearly mark internal code with **`@Internal`**.

### 3.4 Dependency injection

- Avoid field injection.
- Prefer constructor injection and immutability.

References:

- https://docs.micronaut.io/latest/guide/#fieldInjection
- https://docs.micronaut.io/latest/guide/#constructorInjection

### 3.5 Configuration

- Avoid `@Value`.
- Prefer type-safe `@ConfigurationProperties`.

Reference:

- https://docs.micronaut.io/latest/guide/#configurationProperties

Rules for new `@ConfigurationProperties`:

- Define prefix as `public static final String PREFIX`
- Default values must be constants named `DEFAULT_...`
- Use Jakarta validation annotations where appropriate
- Include extensive Javadoc

Example:

```java
@ConfigurationProperties(ConfigurationValidatorConfiguration.PREFIX)
public final class ConfigurationValidatorConfiguration {
    /**
     * Configuration prefix.
     */
    public static final String PREFIX = "micronaut.jsonschema.configuration.validator";
    public static final boolean DEFAULT_CACHE = true;

    /**
     * Whether the validation result should be cached.
     * <p>
     * When enabled, the first computed validation result is cached and returned for subsequent
     * invocations.
     *
     * @return Whether the validation result should be cached. Default value {@value #DEFAULT_CACHE}
     */
    public boolean isCache() {
        return cache;
    }

    /**
     * @param cache Whether the validation result should be cached.
     */
    public void setCache(boolean cache) {
        this.cache = cache;
    }
}
```

### 3.6 Tests

- Prefer JUnit 5 + Java + `@MicronautTest` where possible:
  https://micronaut-projects.github.io/micronaut-test/latest/guide/#junit5
- Add Micronaut Test dependencies via `importMicronautCatalog()` and type-safe Gradle dependencies.
- For compiler-focused tests, Spock and the language-specific harnesses are acceptable (e.g. Java `AbstractTypeElementSpec`).

## 4) Documentation requirements

- Document new features in Asciidoc under `src/main/docs/guide`.
- Always verify doc output:

```bash
./gradlew docs
```

### 4.1 Configuration snippets

Use the `[configuration]` macro for configuration snippets.

### 4.2 Usage examples and snippets

- Prefer multi-language examples.
- Use `test-suite`, `test-suite-groovy`, `test-suite-kotlin` conventions where applicable.
- Use the `snippet:` macro for including code.

### 4.3 Dependency snippets

Do not hard-code Gradle/Maven dependency snippets; use the `dependency:` macro.

## 5) Source control safety

- Do **not** push changes without prompting.
- Work on a branch.
- Do **not** revert commits without prompting.
