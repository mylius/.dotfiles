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

# Pull request reviews

- Resolve a GitHub review thread when you are confident its concern has been addressed and verified.

@host.md

@wayve.md