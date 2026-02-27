# Micronaut Control Panel Guide Patterns

Use this file as concrete evidence from a real Micronaut module guide (`micronaut-projects/micronaut-control-panel`, branch `2.0.x`).

## Structure and TOC

- `src/main/docs/guide/toc.yml` includes both flat and nested sections.
- Parent sections can have a title plus nested section keys:

```yaml
controlPanels:
  title: Available Control Panels
  builtIn: Built-in
  management: Management
```

- This maps to:
  - `src/main/docs/guide/controlPanels.adoc`
  - `src/main/docs/guide/controlPanels/builtIn.adoc`
  - `src/main/docs/guide/controlPanels/management.adoc`

## Dependency Macro Usage

Use `dependency:` macro instead of hardcoded Maven/Gradle snippets.

Observed examples:

- `src/main/docs/guide/quickStart.adoc`

```asciidoc
dependency:io.micronaut.controlpanel:micronaut-control-panel-ui[scope=developmentOnly]
dependency:io.micronaut.controlpanel:micronaut-control-panel-management[scope=developmentOnly]
```

- `src/main/docs/guide/controlPanels/management.adoc`

```asciidoc
dependency:io.micronaut.controlpanel:micronaut-control-panel-management[scope=developmentOnly]
dependency:io.micronaut.:micronaut-management[scope=runtimeOnly]
```

## Generated Config Properties Includes

Prefer generated configuration property includes over handwritten property tables.

Observed examples:

- `src/main/docs/guide/quickStart.adoc`

```asciidoc
include::{includedir}configurationProperties/io.micronaut.controlpanel.core.config.ControlPanelModuleConfiguration.adoc[]
```

- `src/main/docs/guide/controlPanels.adoc`

```asciidoc
include::{includedir}configurationProperties/io.micronaut.controlpanel.core.config.ControlPanelConfiguration.adoc[]
```

## Configuration Snippet Blocks

Use `[configuration]` blocks for config snippets that should render in multiple formats.

Observed examples in `src/main/docs/guide/controlPanels/management.adoc`:

```asciidoc
[configuration]
----
endpoints:
  health:
    details-visible: ANONYMOUS
----
```

## Other Maintainer-Relevant Patterns

- Use environment-specific runtime examples (`MICRONAUT_ENVIRONMENTS=dev`) in shell blocks.
- Keep images in `src/main/docs/resources/img/` and reference by filename (`image::control-panel.png[]` in `src/main/docs/guide/introduction.adoc`).
- Link behavior details to stable official docs URLs (for example endpoint docs in `src/main/docs/guide/controlPanels.adoc`).
