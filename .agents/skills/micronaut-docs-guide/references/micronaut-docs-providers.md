# Micronaut Docs Providers and Macros

This reference captures confirmed behavior from `micronaut-docs` and `micronaut-build` that affects module guide authoring.

## 1) Configuration Property Reference Provider

`micronaut-docs` ships a metadata writer that generates AsciiDoc property reference output:

- Implementation: `docs-asciidoc-config-props/src/main/java/io/micronaut/documentation/asciidoc/AsciiDocPropertyReferenceWriter.java`
- Service registration: `docs-asciidoc-config-props/src/main/resources/META-INF/services/io.micronaut.inject.configuration.ConfigurationMetadataWriter`

What it writes:

- Generates `META-INF/config-properties.adoc` fragments from Micronaut configuration metadata.
- Produces section anchors and property tables (property, type, description, default value).

Implication for maintainers:

- In guide content, prefer includes under `{includedir}configurationProperties/...` instead of manually maintained configuration property tables.

## 2) Asciidoctor Extension Registry Used by Micronaut Build

`micronaut-build` registers the docs-specific Asciidoctor extensions:

- Registry: `micronaut-gradle-plugins/src/main/groovy/io/micronaut/docs/DocsExtensionRegistry.groovy`
- Service loader: `micronaut-gradle-plugins/src/main/resources/META-INF/services/org.asciidoctor.jruby.extension.spi.ExtensionRegistry`

Registered macros/processors include:

- Inline macros: `api`, `mnapi`, `ann`, `pkg`, `jdk`, `jee`, `rs`, `rx`, `reactor`, `dependency`
- Block macro: `snippet`
- Block processor: `configuration`

## 3) `dependency:` Macro Behavior

Implementation: `micronaut-gradle-plugins/src/main/groovy/io/micronaut/docs/BuildDependencyMacro.groovy`

Observed behavior:

1. Accepts `dependency:target[attributes]`.
2. Can parse `group:artifact[:version]` target forms.
3. Defaults to `groupId=io.micronaut` when not provided.
4. Converts scopes between Gradle and Maven (`implementation` -> `compile`, `developmentOnly` -> `provided`, etc.).
5. Renders multi-language dependency snippets for Gradle and Maven.

Maintainer usage guidance:

- Use `dependency:` in docs for dependency instructions so rendering stays consistent across build tools.

## 4) `snippet::` Macro Behavior

Implementation: `micronaut-gradle-plugins/src/main/groovy/io/micronaut/docs/LanguageSnippetMacro.groovy`

Observed behavior:

1. Supports languages `java`, `python`, `kotlin`, `groovy`.
2. Resolves source files from test suite directories (`test-suite`, `test-suite-kotlin`, `test-suite-groovy`, `test-suite-python`) unless overridden.
3. Supports `tags`, `indent`, `title`, `project`, `project-base`, and `source` attributes.
4. Emits `source.multi-language-sample` blocks and converts them through Asciidoctor.

Maintainer usage guidance:

- Prefer `snippet::` for source examples that should stay synchronized with tests.

## 5) `[configuration]` Block Behavior

Implementation: `micronaut-gradle-plugins/src/main/groovy/io/micronaut/docs/ConfigurationPropertiesMacro.groovy`

Observed behavior:

1. Registered as `@Name("configuration")` for listing blocks.
2. Interprets input content as YAML source.
3. Converts output to multiple formats (properties, yaml, toml, groovy-config, hocon, json-config).
4. Emits language-switched samples for docs rendering.

Maintainer usage guidance:

- Use `[configuration]` blocks for settings documentation rather than single-format snippets.

## 6) Build Integration in Micronaut Docs Plugin

Implementation: `micronaut-gradle-plugins/src/main/groovy/io/micronaut/build/MicronautDocsPlugin.groovy`

Relevant configured properties include:

- `safe=UNSAFE`
- `source-highlighter=highlightjs`
- `includedir=<build working includes dir>`
- `api=../api`
- `micronautapi=https://docs.micronaut.io/latest/api/io/micronaut/`
- `default-language` (for language-specific guide rendering)

Guide assembly tasks include `publishGuide*`, `assembleDocs`, and `docs`.
