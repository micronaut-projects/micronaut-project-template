<!-- BEGIN MICRONAUT GLOBAL CONTRIBUTING: Managed by micronaut-project-template/GLOBAL_CONTRIBUTING.md. Do not add or modify content below this marker in this file; your changes will be replaced by the sync workflow. -->
## Shared Micronaut Contribution Guidance

This section is maintained centrally in `micronaut-project-template` and synced into repository `CONTRIBUTING.md` files.

Do not add repository-specific changes below the begin marker above. Add local contribution guidance before that marker instead.

### Pull Request Expectations

- Include tests for behavioral changes.
- Include documentation updates when user-facing behavior changes.
- Link the pull request to the relevant issue when applicable.
- Make sure CI is green before requesting review.

### Code Style

Micronaut projects use Checkstyle and related build checks to keep code style consistent. Run the relevant Gradle verification tasks locally before opening a pull request.

### Branching and Release Awareness

When preparing or reviewing a change, make sure it targets the correct branch for the type of change being made so that patch, minor, and major releases stay aligned.
<!-- END MICRONAUT GLOBAL CONTRIBUTING -->
