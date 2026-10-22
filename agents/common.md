# Agent Instructions

## Mandatory writing style

Apply the `unslop` skill to every user-facing response. Before replying, read and follow `~/.agents/skills/unslop/SKILL.md`; its style rules are mandatory.

# Worktrees

Before editing code or running builds, tests, or lint, create a dedicated clean Git worktree from `main` unless the user names another base. Do not work in the primary checkout or a dirty worktree. Name branches `jangabrielmylius/{product-name}/{meaningful_change_description_short}`.

If work began in the wrong checkout, do not merely report it. Create the correct worktree, reapply or move only the task's changes there, restore the original checkout without disturbing pre-existing changes, and validate from the worktree.

# Execution and recovery

Work autonomously until the requested outcome is complete. A routine command, test, build, dependency, authentication, or environment failure is not a stopping point.

When an issue occurs:

1. Inspect the concrete error and relevant code, configuration, documentation, or loaded skill.
2. Apply the smallest safe, reversible fix or run the documented recovery command.
3. Re-run the failed operation and targeted checks. Do not merely tell the user which command should be run.
4. Continue until the task is complete or a genuine blocker remains you can't unblock.

A steering or follow-up message changes the task but does not cancel unfinished recovery or validation unless the user explicitly cancels it or the new request makes it obsolete.

Ask only when a decision or user action is genuinely required, such as ambiguous product behavior, missing credentials, an interactive browser/device login, an unavailable external system, or a destructive, irreversible, security-sensitive, or out-of-scope action. Before asking, perform every safe non-interactive step available. When blocked, give the exact blocker, concrete diagnostics, what was tried, and one recommended next action.

Before finishing, report the validation actually run and its result. Do not claim success without verification. Never guess missing facts, expose secrets, change access controls, or perform destructive or unrelated external actions.

# Delegation

Hand tedious, mechanical work to a cheap subagent so the main context keeps the conclusion instead of the raw output. Claude delegates to Claude Haiku 5.5 (`claude-haiku-5-5`). Codex delegates to GPT-6 Luna (`gpt-6-luna`). This covers:

- running tests, lint, type checks, and builds, then reporting each failure with file, line, and error text
- searching a codebase for symbols, call sites, config keys, or naming patterns
- reading logs, CI output, or long files to pull out specific facts
- collecting data in bulk, such as listing worktrees, branches, or transcript statistics

Run independent subagents in parallel. Give each one the exact command or question, the worktree path, and the shape of the answer you want back. Keep design decisions, edits that need judgment, code review, and anything with side effects outside the worktree on the main model. Skip delegation when one command or one known file answers the question.

Check what a subagent reports before acting on it. If it says a check failed, re-run that one check yourself before fixing anything.

To launch one:

- Claude: the Agent tool with `model: "haiku"`. In T3 Code, if that tool can't select Haiku, use `delegate_task` with provider `claudeAgent` and model `claude-haiku-5-5`.
- Codex: the native subagent tool with `gpt-6-luna`. In T3 Code, if that tool can't select Luna, use `delegate_task` with provider `codex` and model `gpt-6-luna`.

# Pull request reviews

- Resolve a GitHub review thread when you are confident its concern has been addressed and verified.

@host.md

@wayve.md