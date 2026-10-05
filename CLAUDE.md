<!--
Notes for maintainers. Claude Code strips HTML comments before the model reads this file.
- By default, Claude Code skips AGENTS.md files, nested ones included, when a CLAUDE.md, .claude/CLAUDE.md or
  CLAUDE.local.md exists, so this file imports the root AGENTS.md.
- Repository facts go in AGENTS.md; only rules specific to Claude Code and Claude models go here.
- .claude/skills links to .agents/skills. files-sync.yml copies neither this file nor .claude/, so a generated
  repository keeps the copy it was created with.
-->

@AGENTS.md

# Claude Code

- If the shared skills are missing from your skill list (no symlinks, as on Windows by default), read them in `.agents/skills/`.
- Outside micronaut-project-template, the nightly files sync overwrites `.agents/skills`, where `.claude/skills` points. Give each skill file you add or edit there a `<file>.lock` beside it (such as `SKILL.md.lock`), or the sync deletes or reverts it.
- Pick the base branch before you write code: fixes go to the branch whose `projectVersion` is the next patch of the latest release, features to the next minor. The default branch can be either. Maintainers merge fixes up; open backports or forward ports only when asked.
- Fix the cause in the module or repository that owns it. Do not add fallbacks that hide a failure.
- Your knowledge of Micronaut APIs, the Gradle DSL and library versions is out of date. Check the target branch's sources, its version catalog and Maven Central.
- Defaults and observable behavior count as API: write each behavior change into the guide's Breaking Changes section, even in a minor release.
- Document in the guide what users see or must set, with its costs (such as image size). Opt-in optimizations and internal switches get Javadoc only.
- Do not run `./gradlew --stop` or kill processes you did not start.
- Show that each new test fails without the change. Run every language test suite the change reaches, and `nativeTest` where the build has it when service loading, reflection or static initialization change.
- `gradle.yml` skips draft pull requests. Run the checks locally, say which you did not run, and reproduce a failure on the base branch before you call it pre-existing.
- Call a single run a probe. A performance claim needs paired, interleaved runs with 95% intervals on a named quiet machine, measured on the application as users package it, with a harness reviewers can rerun. Give relative numbers, and name any non-default flag the gain needs in the title.
- Run `/code-review` on the diff before handing over.
- Keep pull request descriptions to about 250 words with at most one small table: what changes and why, how users opt in or out, how you tested it. Keep replies to a few sentences. Write plain prose without bold, emoji, raw logs, or headings that `CONTRIBUTING.md` does not require. Put `Fixes #N` in the description, never in a commit message, and update the description when a push makes it wrong.
- Once a pull request is under review, merge the base branch in instead of rebasing or force-pushing, then rerun the tests and re-measure any performance claim. Retarget with `gh pr edit --base`, never with a second pull request.
- Verify each reviewer or bot finding before you act on it. Fix a real one with a test; answer a wrong bot finding once with evidence. Do not resolve threads.
- Open pull requests as drafts. Leave marking ready, requesting review, merging, closing and releasing to the user, and draft for the user any reply that disagrees with a maintainer or discusses scope or tone.
