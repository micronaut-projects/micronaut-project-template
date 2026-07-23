<!-- BEGIN MICRONAUT GLOBAL CONTRIBUTING: Managed by micronaut-project-template/GLOBAL_CONTRIBUTING.md. Do not add or modify content below this marker in this file; your changes will be replaced by the sync workflow. -->
## Shared Micronaut Contribution Guidance

This section is maintained centrally in `micronaut-project-template` and synced into repository `CONTRIBUTING.md` files.

Do not add repository-specific changes below the begin marker above. Add local contribution guidance before that marker instead.

### Model Used (Required)

Every PR must include a **Model Used** section specifying which AI model produced or assisted with the change. Include the provider, exact model ID/version, context window size, and any relevant capability details (e.g., reasoning mode, tool use). If no AI was used, write "None — human-authored". This applies to all contributors — human and AI alike.

### CI Must Pass

All tests must pass before a PR can be merged. Run them locally first and verify CI is green after pushing.

### Copilot Review

We use [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/code-review) for automated code review. Your PR must have **all Copilot comments addressed** before it can be merged. If Copilot leaves comments, fix or respond to each one and request a re-review.

<!-- END MICRONAUT GLOBAL CONTRIBUTING -->
