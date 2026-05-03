# Repository Guidance

This repository is the Micronaut template for generated module repositories. Keep root guidance short and update it when the template workflow changes.

## Repository Shape

- `project-template/` is the generated module placeholder. Changes here should make sense after `template-cleanup.yml` renames it to `micronaut-<slug>/`.
- `project-template-bom/` is the generated BOM placeholder. Keep dependency-management changes separate from module implementation changes when possible.
- `buildSrc/src/main/groovy/io.micronaut.build.internal.project-template-*.gradle` contains template convention plugins that are also renamed by the cleanup workflow.
- `.agents/skills/` is shared agent guidance. Skill changes are validated by `.github/workflows/skills-validation.yml`.

## Template And Sync Rules

- Treat `.github/workflows/files-sync.yml` as the source of truth for files copied from this template to other Micronaut repositories.
- Before editing synced files, check whether the file is copied by `files-sync.yml`, excluded by `.github/workflows/.rsync-filter`, or rewritten by `.github/workflows/template-cleanup.yml`.
- `CONTRIBUTING.md` is rewritten by `template-cleanup.yml` when a repository is created from the template, but it is not copied by the recurring files-sync workflow. Existing downstream copies need repo-specific PRs.
- Do not add project-specific assumptions to files that will be synced broadly unless the cleanup workflow rewrites them correctly for generated repositories.
- When changing placeholder names, update every cleanup substitution and related file move in `.github/workflows/template-cleanup.yml`.

## Documentation

- User guide sources live in `src/main/docs/guide`, with navigation in `src/main/docs/guide/toc.yml`.
- Build guide output with `./gradlew publishGuide` or `./gradlew pG`; build guide plus Javadocs with `./gradlew docs`.
- There are currently no `doc-examples/` snippets or shared docs images in this template. Prefer runnable snippets if examples are introduced.
- Release-note behavior is maintained through `.github/release.yml`, `.github/workflows/release.yml`, and the release process documented in `MAINTAINING.md`.

## Verification

- Use `./gradlew check` for general validation.
- Use `./gradlew publishGuide` after guide or `toc.yml` changes.
- Use `./gradlew docs` when API docs or release documentation output matters.
- For `.agents/skills/**` changes, run the same validation as `skills-validation.yml` for the touched skill directories.
