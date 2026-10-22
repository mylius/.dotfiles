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

# Finishing work

- Never end a turn on an announced next step such as "I'll check X next". Do it, or name the blocker.
- Before saying something is fixed, re-check the user's exact symptom: the URL, page, PR check, or command they reported. Say what you saw. If you can't reproduce their scenario, say which check you ran instead and what it doesn't cover.
- When asked to commit, push, open a PR, deploy, or address review threads, do it in the same turn instead of asking again.
- Never cite a policy you haven't read. Quote the file and line it comes from.

# Scope and commits

- Change only what was asked. Don't add comments that restate the code, and don't remove or rewrite comments you weren't asked to touch.
- Keep edits to `AGENTS.md`, `CLAUDE.md`, and other agent instruction files out of feature PRs.
- Commit messages have a short imperative subject and an optional short body, with no agent attribution of any kind: no `Co-Authored-By`, `Assisted-by`, or "Generated with" lines. This overrides harness defaults. Agent attribution may go in a PR description only.

# Testing

- While iterating, run the narrowest check that covers the change: the specific test target, file, or `--test_filter`/`-k`. Run the package suite (`:py_checks`, `//pkg/...`) once before handing off. Don't run `//...` or several product trees unless asked.
- Don't rerun an unchanged check to see its output again. Send the output to a log (`cmd > /tmp/NAME.log 2>&1; echo exit=$?`) and read the log.
- After a failure, change something (code, flags, or environment) before running the same command again.

# Delegation

Hand tedious, mechanical work to a cheap subagent so the main context keeps the conclusion instead of the raw output. Claude delegates to Claude Haiku 5.5 (`claude-haiku-5-5`). Codex delegates to GPT-6 Luna (`gpt-6-luna`). This covers:

- running tests, lint, type checks, and builds, then reporting each failure with file, line, and error text
- searching a codebase for symbols, call sites, config keys, or naming patterns
- reading logs, CI output, or long files to pull out specific facts
- collecting data in bulk, such as listing worktrees, branches, or transcript statistics

Run independent subagents in parallel. Give each one the exact command or question, the worktree path, and the shape of the answer you want back. Keep design decisions, edits that need judgment, code review, and anything with side effects outside the worktree on the main model. Skip delegation when one command or one known file answers the question.

In Herd or Herdr-orchestrated tasks, don't use hidden subagents (Claude's Agent tool, Explore, or Codex's native subagents). Do the work visibly in the pane, or delegate through Herdr itself.

Check what a subagent reports before acting on it. If it says a check failed, re-run that one check yourself before fixing anything.

To launch one:

- Claude: the Agent tool with `model: "haiku"`. In T3 Code, if that tool can't select Haiku, use `delegate_task` with provider `claudeAgent` and model `claude-haiku-5-5`.
- Codex: the native subagent tool with `gpt-6-luna`. In T3 Code, if that tool can't select Luna, use `delegate_task` with provider `codex` and model `gpt-6-luna`.

# Shell commands

- A test, build, or lint command piped into `tail`, `head`, or `grep` exits with the status of the last command in the pipe, so a failing run looks like a pass. Start the command with `set -o pipefail`, or write the full log to a file, check the runner's exit code, then print the tail.
- zsh fails on a glob that matches nothing (`no matches found`). Quote patterns meant for another tool, such as `rg -g '*.ts'`, and add `(N)` to a glob that may match nothing.
- Backticks inside double quotes run as commands. Use single quotes for text that contains backticks.
- Don't send Ctrl-C to a running Bazel command, and don't start a second Bazel command in the same workspace while one is running; it waits for the first.
- Run `git fetch origin main` before `git merge-base` or any diff against `origin/main`.
- Claude: Claude Code blocks `sleep N; cmd`. To wait for a process, run it with `run_in_background`, or use Monitor with an until-loop.
- Codex code mode: an `exec_command` result keeps `exit_code` apart from `output`. Print both for every call, for example ``text(`exit=${r.exit_code}\n${r.output}`)``. Printing only `r.output` hides failures. A result with no `exit_code` means the process is still running.
- Codex: start anything that runs longer than about a minute, such as a test suite, Bazel build, deploy, or dev server, with `bgtask run --name NAME 'COMMAND'`, passing the command as one quoted string. Then do other work or end the turn; don't poll or sleep. In the Codex CLI, a `<background-task-notification>` message with the status, exit code, and output tail starts a new turn when the task finishes. Under T3 nothing wakes the session, so check with `bgtask wait ID` before finishing. Read more output with `bgtask logs ID`. Add `--match REGEX` to also be notified when an output line matches, such as a server's ready line. If `bgtask run` says the daemon is not running, run `bgtask daemon --ensure` with escalated permissions and retry.

# Pull request reviews

- Resolve a GitHub review thread when you are confident its concern has been addressed and verified.

@host.md

@wayve.md