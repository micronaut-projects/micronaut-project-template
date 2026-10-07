---
name: pull-request
description: Commit changes and create pull requests
license: Apache-2.0
compatibility: Git repositories with GitHub upstream
metadata:
  author: Jonas Konrad
  version: "1.0"
---

# Pull Requests

This skill helps with committing changes and creating pull requests against repositories in the micronaut-projects github organization.

## Committing changes

Do not commit changes unless asked to.

When creating commits, use the default Git "Author", but add a "Co-Authored-By" tag with the AI agent that created the commit.

## Creating pull requests

Do not create pull requests unless asked to.

1. Verify the github CLI is installed and authenticated: `gh auth status` – If this is not the case, inform the user.
2. Identify the branch the change will be made against. Micronaut projects use semantic versioning with one branch per minor release. For example, the 4.10.8 release is on the 4.10.x branch. There are independent semantic versions for each project.
3. Create the PR.
4. Check the GitHub releases for the latest release of this minor version. Your patch will be part of the next patch release associated with the branch you are working on. For example, if 4.10.8 is the latest patch release for the 4.10.x branch, your PR will be in the 4.10.9 release.
5. If there is no release for a branch yet, the patch will be part of the first version of that minor, e.g. 4.10.0.
6. Associate the PR with the milestone for its patch release. If no such milestone exists, create it.
7. Add the following labels to the PR (mutually exclusive):
  * "type: bug" If this PR is a bug fix
  * "type: improvement" If this PR contains a minor feature
  * "type: enhancement" If this PR contains a major feature
  * "type: docs" If this PR contains only documentation changes
  * "type: breaking" If this PR contains a breaking change (not mutually exclusive, can be used with other "type" labels)

If the change resolves a particular issue, the PR text should contain "Fixes #123".

All PRs will be squashed before merging, so it is not necessary to keep a clean commit history inside a PR. Avoid rebasing and force pushing, prefer merging.
