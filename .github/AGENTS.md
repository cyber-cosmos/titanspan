# GitHub configuration instructions

Follow root `AGENTS.md`, `SECURITY.md`, and `CONTRIBUTING.md`. This directory
contains repository governance and CI, not framework runtime code.

- Use least-privilege workflow permissions and pin third-party actions to
  verified immutable commits where practical.
- Keep required checks aligned with `make check`; preserve locked uv installs.
- Do not weaken required CI, dependency auditing, secret detection, or
  repository protection to make a change pass.
- Do not add action tokens, secrets, model/provider configuration, MCP
  servers, arbitrary hooks, or blanket command permissions.
- Keep issue forms, pull request templates, workflows, and Copilot agent
  profiles accurate and reviewable. Copilot profiles must remain optional,
  omit model identifiers, and use read-only tools for reviewers.
- Verify action versions, schemas, and platform behavior against official
  documentation before changing workflow configuration.
- Run `make agents-check` after agent configuration changes. Validate
  workflow syntax with available tooling and report when validation is
  unavailable.
