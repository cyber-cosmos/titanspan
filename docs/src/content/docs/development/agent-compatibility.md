---
title: "Coding agent compatibility"
---

<span id="coding-agent-compatibility"></span>

This guide records repository instruction discovery reviewed against official
product documentation on **2026-11-24**. Compatibility here means a documented
repository-level path or a documented manual-context workflow. It does not
mean a harness was installed or runtime-tested. No coding agent was installed
or invoked for this review.

`AGENTS.md` is the canonical instruction source. Shared skills live under
`.agents/skills/` and follow the [Agent Skills specification](https://agentskills.io/specification).
Adapters are intentionally short. The skills remain optional and load on
demand; they do not add runtime dependencies or framework behavior.

## Compatibility matrix

**Status meanings:** `Verified through actual local testing` means the
repository setup was exercised in that harness. `Verified against official
documentation` means current official documentation describes the mechanism.
`Partially supported` means a documented limitation remains. `Manual
configuration required` means attach or paste root `AGENTS.md` and relevant
documents. `Unsupported` and `Not verified` mean no compatible mechanism was
confirmed. No row below is runtime-tested.

| Harness | Repository instruction discovery | Scope and skills | Hooks, permissions, or limitation | Status and official documentation |
| --- | --- | --- | --- | --- |
| OpenAI Codex | Root and nested `AGENTS.md` | Nested instructions; `.agents/skills/` | Project config and hooks can affect tool behavior; none are configured here. | Verified against official documentation; [AGENTS](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [skills](https://learn.chatgpt.com/docs/build-skills) |
| Claude Code | Reads `AGENTS.md` natively in current versions when no ancestor `CLAUDE.md` overrides it; `CLAUDE.md` imports canonical `AGENTS.md` for older or opt-in sessions. | Nested instructions; `.claude/rules/` and `.claude/skills/` are supported. Canonical `.agents/skills/` are not auto-discovered by the cited docs. | Hooks and permission settings exist; this repository sets neither. Direct AGENTS support requires Claude Code 2.1.277+. | Verified against official documentation; [memory and AGENTS](https://code.claude.com/docs/en/memory), [skills](https://code.claude.com/docs/en/skills) |
| Claude Agent SDK | Project files load only when the SDK caller enables project settings; use the `CLAUDE.md` adapter. | Same `.claude/` project capabilities when loaded; caller controls settings sources. Canonical skills need a `.claude/skills/` location to be slash-invokable. | SDK settings, tools, hooks, and permissions are caller-controlled. No SDK or model dependency is added. | Partially supported; [SDK overview](https://code.claude.com/docs/en/agent-sdk/overview), [configuration](https://code.claude.com/docs/en/agent-sdk/configuration) |
| Gemini CLI | `.gemini/settings.json` selects `AGENTS.md` as its context filename. | Its context discovery is hierarchical; `.agents/skills/` is a workspace skill path. | Settings support hooks and policy controls; none are configured. Skill activation may require user consent. | Verified against official documentation; [configuration](https://geminicli.com/docs/reference/configuration/), [skills](https://geminicli.com/docs/cli/using-agent-skills/) |
| Gemini Code Assist | No repository instruction filename was verified. Use its IDE context/custom-rule controls to attach `AGENTS.md`. | File/folder context and custom rules depend on the IDE surface; no skill discovery path verified. | Some code-customization features require an Enterprise subscription; ordinary manual context remains available. | Manual configuration required; [chat and context](https://docs.cloud.google.com/gemini/docs/codeassist/chat-gemini), [customization](https://docs.cloud.google.com/gemini/docs/codeassist/use-code-customization) |
| Antigravity | Root `AGENTS.md` is automatically loaded. | `.agents/skills/` is native. Nested `AGENTS.md` below a root workspace is not scanned automatically; open the relevant subtree as a workspace for scoped rules. | Native hooks, agents, and permission surfaces exist; no hooks or permission overrides are added. | Partially supported; [discovery](https://antigravity.google/docs/customization-discovery/), [skills](https://antigravity.google/docs/skills/) |
| GitHub Copilot (IDE) | Reads root and nearest `AGENTS.md`; optional profiles are in `.github/agents/`. | Path-scoped AGENTS support varies by client; `.agents/skills/` is recognized on documented surfaces. | Specialist profiles are explicit-invocation only; reviewers have read/search tools only. | Verified against official documentation; [instructions](https://docs.github.com/en/copilot/concepts/prompting-and-context/custom-instructions), [skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills), [profiles](https://docs.github.com/en/copilot/reference/custom-agents-configuration) |
| GitHub Copilot CLI | Reads repository `AGENTS.md` and repository instruction files. | Nested instructions and `.agents/skills/` are supported. | Tool approval behavior belongs to the selected CLI configuration; this repo does not override it. | Verified against official documentation; [CLI customization](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions), [skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) |
| Cursor | Root and nested `AGENTS.md` are supported. | Nested AGENTS scope to their subtrees; `.agents/skills/` is native. | Project hooks exist but are not configured. | Verified against official documentation; [rules](https://cursor.com/docs/rules), [skills](https://cursor.com/docs/skills), [hooks](https://cursor.com/docs/hooks) |
| Windsurf / Devin Desktop | Current Devin Desktop documentation supports root and nested `AGENTS.md`; older Windsurf releases may differ. | `.agents/skills/` compatibility is documented for current Devin tooling; check the selected surface/version. | Native rules and skills are available; no project permission changes are made. | Partially supported; current Devin Desktop only; [customizations](https://docs.devin.ai/desktop/devin-local/customizations) |
| Devin (cloud agent) | Repository setup and knowledge are configured in Devin; automatic `AGENTS.md` discovery was not verified for every cloud surface. Attach `AGENTS.md` as repository context. | Skills may be used where the Devin surface documents them; cloud setup varies by workspace. | Cloud repository setup can run environment commands; use maintainer review before changing it. | Manual configuration required; [repository setup](https://docs.devin.ai/onboard-devin/environment) |
| Cline | Detects root `AGENTS.md`, but detected rules appear in the Rules panel and may need enabling. | Native path-specific rule support is documented in `.clinerules/`; native skills live under `.cline/skills/`. The shared `.agents/skills/` are not auto-discovered; read the relevant `SKILL.md` manually. | Cline owns rule toggles and tool approval; this repository changes neither. Nested AGENTS behavior is not confirmed by the cited docs. | Partially supported; [rules](https://docs.cline.bot/customization/cline-rules), [skills](https://docs.cline.bot/customization/skills) |
| Roo Code | Root `AGENTS.md` is loaded by default. | Nested rules and `.agents/skills/` are supported. | Modes, tools, and approval behavior are controlled by Roo; no repository override is added. | Verified against official documentation; [instructions](https://roocodeinc.github.io/Roo-Code/features/custom-instructions/), [skills](https://roocodeinc.github.io/Roo-Code/features/skills/) |
| OpenCode | Root and nested `AGENTS.md` are discovered. | Nested instruction files; `.agents/skills/` is a native compatibility path. | V2 supports project agents and ordered permissions; no `opencode.json` policy is added. | Verified against official documentation; [instructions](https://opencode.ai/docs/instructions), [skills](https://opencode.ai/docs/skills), [permissions](https://opencode.ai/docs/permissions/) |
| Aider | `.aider.conf.yml` loads root `AGENTS.md` read-only. | No automatic nested instruction or reusable skills mechanism verified; `/read` a nearest scoped file when needed. | Aider can execute suggested shell commands; the config does not enable auto-approval or choose a model. | Verified against official documentation; [configuration](https://aider.chat/docs/config/aider_conf.html), [conventions](https://aider.chat/docs/usage/conventions.html) |
| Continue | `.continue/rules/` is the native rules path; an always-applied adapter points to `AGENTS.md`. | Rules are always-applied; no project skill path was verified for the selected Continue setup. | Tool controls are managed by the chosen Continue agent/configuration; not changed here. | Verified against official documentation; [rules](https://docs.continue.dev/customize/rules), [rule syntax](https://docs.continue.dev/customize/deep-dives/rules) |
| Goose | Reads `AGENTS.md` and `.goosehints` context files by default, including nested instructions. | `.agents/skills/` is supported by its Agent Skills discovery. | Hooks/extensions and permissions are runtime features; no `.goosehints`, extension, or permission policy is added. | Verified against official documentation; [context files](https://goose-docs.ai/docs/guides/context-engineering/using-goosehints/), [skills](https://goose-docs.ai/docs/guides/context-engineering/using-skills/) |
| Qwen Code | Reads `AGENTS.md` alongside its own context files. | `.agents/skills/` project skills are native. | Settings/policies may govern tools and skills; no model or permission values are set. | Verified against official documentation; [memory](https://qwenlm.github.io/qwen-code-docs/en/users/features/memory/), [skills](https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/) |
| Amazon Q Developer | `.amazonq/rules/` adapter gives concise rules and directs the agent to canonical docs. | Markdown rules; no shared skill path verified. | IDE tool permissions remain user-managed. | Verified against official documentation; [project rules](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/context-project-rules.html) |
| Kiro | Reads root and scoped `AGENTS.md`; native `.kiro/steering/` can import files. | Native skill path is `.kiro/skills/`; use the canonical `.agents/skills/` files manually or import them when needed. | Hooks and agent permissions are available, but none are configured. | Verified against official documentation; [steering](https://kiro.dev/docs/steering/), [skills](https://kiro.dev/docs/cli/skills/) |
| Junie | Reads root `AGENTS.md`; `.junie/AGENTS.md` can override, so do not create one here. | Shared `.agents/skills/` and `.junie/skills/` are supported. | Junie playbooks/rules are optional; approval remains IDE-managed. | Verified against official documentation; [guidelines](https://junie.jetbrains.com/docs/guidelines-and-memory.html), [skills](https://junie.jetbrains.com/docs/agent-skills.html) |
| JetBrains AI Assistant | `.aiassistant/rules/titanspan.md` is a manual adapter; select rule type **Always** in IDE settings. | Markdown rules can be manual, always, model-selected, or file-pattern-scoped. No shared skill mechanism was verified. | Rule activation is a user IDE setting; no project permission overrides are made. | Manual configuration required; [project rules](https://www.jetbrains.com/help/ai-assistant/configure-project-rules.html) |
| Augment Code | Reads root and scoped `AGENTS.md`; no adapter is needed. | Native rules; check current surface for skill behavior. | Permission controls vary by Augment surface; no tool or permission policy is changed. | Verified against official documentation; [rules](https://www.augmentcode.com/changelog/introducing-augment-rules), [AGENTS and scope](https://www.augmentcode.com/guides/agents-md-vs-claude-md) |
| Zed Agent | Reads repository `AGENTS.md` instructions. | The open skills path is `.agents/skills/`; nested guidance depends on the current Zed surface. | Tool calls remain subject to Zed's user approval controls. | Verified against official documentation; [instructions](https://zed.dev/docs/ai/instructions), [skills](https://zed.dev/docs/ai/skills) |
| Trae | `.trae/rules/titanspan.md` is the native adapter. `AGENTS.md` import requires enabling the corresponding IDE setting. | Rule scope/activation depends on the selected Trae IDE version; no shared skill path verified. | Trust the repository and enable AGENTS import in Settings > Rules if using that feature; this repository does not alter tool permissions. | Partially supported; [project rules](https://docs.trae.cn/ide_rules) |
| Amp | Root and nested `AGENTS.md` are native. | `.agents/skills/` is native. | Plugins may add hooks/tools; no plugin or hook is included. | Verified against official documentation; [AGENTS](https://ampcode.com/docs/customize/agents-md), [skills](https://ampcode.com/manual#agent-skills) |
| Factory Droid | Root and nested `AGENTS.md` are native. | `.agents/skills/` is a documented compatibility location. | Factory exposes project droids and tool policies; no project droid or settings policy is added. | Verified against official documentation; [AGENTS](https://docs.factory.com/harness/agents-md), [skills](https://docs.factory.com/harness/skills) |
| Warp | Root and nested `AGENTS.md` are native project rules. | The Warp CLI shares project rules and skills; `.agents/skills/` is the shared skills path. | Approval and permission settings remain local to the selected Warp surface. | Verified against official documentation; [project rules](https://docs.warp.dev/agents/capabilities/rules/), [CLI](https://docs.warp.dev/agents/cli/configuration) |
| Tabnine | `.tabnine/guidelines/` adapter links to `AGENTS.md` and carries key constraints. | Markdown guidelines; no shared skill path verified. | Tool operation is governed by the user's Tabnine configuration. | Verified against official documentation; [guidelines](https://docs.tabnine.com/main/getting-started/tabnine-agent/guidelines) |

## Instruction precedence and activation

Repository-level instruction support does not imply one shared precedence
algorithm across all products. Use only the behavior each vendor documents:

- Codex, Cursor, OpenCode, Goose, and other AGENTS-aware clients apply root
  guidance with more-specific path guidance where their docs describe nested
  discovery. Read the applicable scoped `AGENTS.md` when changing that area.
- Claude Code versions that recognize `AGENTS.md` skip it when an ancestor
  `CLAUDE.md` is present. This repository's root `CLAUDE.md` imports
  `AGENTS.md`, so both current and older Claude Code paths reach the same
  source. Agent SDK callers must include the project settings source for
  `CLAUDE.md` and project skills to load.
- Gemini CLI uses the configured `context.fileName` list and hierarchical
  context discovery. The repository setting selects `AGENTS.md`; nested
  instructions are available by path.
- Copilot clients can combine custom instructions; there is no single
  cross-surface ordering guarantee. The custom profiles explicitly include
  repository instructions. Path-specific behavior varies by client.
- Cline combines detected rules, but its Rules panel can disable a rule.
  Workspace rules take precedence over global rules. Root `AGENTS.md` must
  remain enabled; nested `AGENTS.md` precedence is not established by the
  cited Cline docs.
- Goose loads root `AGENTS.md` by default and discovers nested instruction
  files as it works in those directories. No `.goosehints` file is needed.
- Aider's `read:` setting loads the root instruction file only. Its scoped
  guidance must be explicitly added with `/read` when needed.
- Continue's adapter is always applied. No separate rule ordering is encoded.
- Amazon Q loads `.amazonq/rules/` as project guidance; this repository keeps
  its rule short and points to the canonical documents.
- Kiro steering and rule imports depend on user-selected steering files;
  this repository does not add a second copy of the canonical instructions.
- Junie supports root `AGENTS.md` and its own scoped instruction conventions.
  No `.junie/AGENTS.md` is added because its precedence can override the root.
- JetBrains AI Assistant only applies the adapter when a developer selects
  the **Always** rule type in the IDE.
- Trae requires a trusted project for project rules. Importing `AGENTS.md`
  also requires enabling its IDE setting; the `.trae` adapter is separately
  marked `alwaysApply: true`.
- For other products where the official docs do not specify conflict
  tie-breaking, precedence is not claimed here. Attach root `AGENTS.md` and
  relevant scoped guidance explicitly if a session does not load them.

## Repository adapters

| Path | Purpose |
| --- | --- |
| `CLAUDE.md` | Imports `AGENTS.md` for Claude Code versions/sessions that only load `CLAUDE.md`, and SDK callers that opt into project configuration. |
| `.gemini/settings.json` | Configures Gemini CLI context discovery to read `AGENTS.md`, including nested scope. |
| `.aider.conf.yml` | Loads `AGENTS.md` as Aider read-only context without choosing a provider or model. |
| `.continue/rules/titanspan.md` | Points Continue at the canonical rules and key standards. |
| `.amazonq/rules/titanspan.md` | Gives Amazon Q the required subset and canonical references. |
| `.aiassistant/rules/titanspan.md` | Manual JetBrains rule; users activate it as **Always**. |
| `.trae/rules/titanspan.md` | Always-applied Trae project rule with canonical references. |
| `.tabnine/guidelines/titanspan.md` | Provides Tabnine's repository guideline format. |

Adapters do not contain provider credentials, model identifiers, automatic
installers, external service configuration, permission bypasses, or hooks.

## Optional specialist agents

The `.github/agents/*.agent.md` profiles are optional GitHub Copilot profiles.
They omit model identifiers, set `infer: false` to avoid auto-delegation, and
include canonical repository instructions when invoked as a subagent. Reviewer
profiles are read-only. The same `.agents/skills/` are available to compatible
harnesses; no profile is required for routine tasks.

## Scoped instruction discovery limits

Root `AGENTS.md` applies repository-wide. Additional scoped files exist only
for implemented package modules, tests, benchmarks, docs, examples, and GitHub
configuration. Antigravity's current documentation says a root workspace
does not scan nested `AGENTS.md` files; open the specific subtree as a
workspace for those extra rules. Aider's static `read:` setting loads only the
root file; use `/read path/to/AGENTS.md` when a task needs scoped instructions.
Other clients may differ by version, workspace root, trust, or feature surface.

## Manual use

For any unsupported or unverified harness, open or attach root `AGENTS.md` and
the relevant scoped instructions, then provide links or file paths to the
architecture documents, applicable ADRs, standards, and workflow. Preserve
your chosen model, provider, sandbox, and approval settings.

## Sources and update policy

Each matrix row links to official product documentation. Review these sources
before changing a path or schema because agent discovery behavior changes
frequently. Update the verification date and this matrix when documentation
changes. Run `make agents-check` after editing this compatibility guide or an
adapter. A static check is not runtime testing of a harness. Some harnesses
discover `.agents/skills/` directly; for others, read the relevant skill file
as context or use the harness's documented native skill directory.
