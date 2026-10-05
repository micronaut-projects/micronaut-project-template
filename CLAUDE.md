# Claude Code Guidance for Micronaut Project Template

@AGENTS.md

## Claude Code Configuration

Claude Code sessions in this repository benefit from pre-configured skills and settings aligned with the Micronaut framework. This file builds on the generic `AGENTS.md` guidance with Claude-specific setup and best practices.

## Shared Skills

The repository's `.agents/skills/` directory contains shared guidance for all agents working on Micronaut repositories. Claude Code accesses these skills via a symlink from `.claude/skills/`:

```bash
# If setting up the repository locally for the first time:
ln -s ../.agents/skills .claude/skills
```

On Windows without Administrator privileges or Developer Mode, use the `@import` approach in CLAUDE.md instead:

```markdown
@.agents/skills/coding/SKILL.md
@.agents/skills/gradle/SKILL.md
```

Available skills include:
- **coding**: Micronaut framework Java implementation using maintainer standards (JSpecify null-safety, binary compatibility, framework patterns)
- **gradle**: Gradle configuration, Micronaut build plugins, dependency management
- **docs**: Documentation authoring, guide building, API documentation
- **guides**: Guide authoring, navigation, and publication workflows
- **agent-md-refactor**: Refactoring instruction files for clarity and consistency
- **skill-creator**: Creating and improving agent skills and workflows

## Settings and Permissions

The `.claude/settings.json` file in this repository pre-approves common tools to reduce permission prompts:

- `git` — version control operations
- `./gradlew` — Gradle build tool
- `gh` — GitHub CLI for issue and PR automation

Personal settings (API keys, sandbox URLs, local environment variables) belong in `.claude/settings.local.json`, which is gitignored. See the `.gitignore` entry below.

## Recommended `.gitignore` Entries

Add these lines to `.gitignore` to protect personal Claude Code configuration:

```gitignore
# Claude Code local configuration
CLAUDE.local.md
.claude/settings.local.json
```

The `CLAUDE.md` file itself (this file) is committed for the entire team. Personal project preferences (`.claude/settings.local.json`) stay local.

## Coding Standards

This repository uses Micronaut framework conventions. Additional guidance:

- **API Stability**: Run `./gradlew japiCmp` after API-facing changes to verify binary compatibility
- **Null-safety**: Use JSpecify annotations (`@Nullable`, `@NonNull`) consistently
- **Tests**: Framework tests are comprehensive; use `/coding` skill for maintainer-ready implementations
- **Verification**: Always run `./gradlew check` before committing; `./gradlew docs` for documentation changes

## Avoid These Patterns

Claude models tend toward certain anti-patterns in JVM/Gradle projects. Explicit guidance helps:

- ❌ Do not suggest refactors unless specifically asked
- ❌ Do not add optional logging or observability "for future use"
- ❌ Do not guess performance numbers; use profilers or quote sources
- ❌ Do not claim success without running verification commands
- ❌ Do not alter build configuration unless required by the task

## Getting Help

- **Project structure and conventions**: Read `AGENTS.md` and skill descriptions
- **Build issues**: Run `/debug` for structured troubleshooting or `/run` to test locally
- **Documentation**: Use the `/docs` skill for guide and API doc changes
- **Implementation questions**: Use the `/coding` skill for maintainer standards

## Reporting Issues

If Claude Code's guidance becomes outdated or conflicts with repository practices, open an issue against [micronaut-project-template](https://github.com/micronaut-projects/micronaut-project-template) or contact the Micronaut team.

