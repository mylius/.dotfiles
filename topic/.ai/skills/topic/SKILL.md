---
name: topic
description: Manage branch-scoped git worktrees with `topic`. Use when the user asks to create, switch, list, remove, or purge development topics/branches, or wants to work on a new feature/fix in an isolated worktree. Avoids polluting tmux with sessions for agent-driven workflows.
metadata:
  short-description: Create and manage isolated per-branch worktrees via the `topic` CLI
---

# topic

`topic` is the user's workflow command for managing git worktrees as per-branch "topics". Each topic is a worktree at `/workspace/wt/<repo>/<branch-sanitized>/`. When run interactively, `topic` also owns a paired tmux session; agent invocations skip session creation.

## When to use

- User asks to "start a new topic", "work on X", "spin up a branch", or gives a branch name and a task
- User asks to list, switch between, remove, or purge topics
- User mentions checking out an existing remote branch for work

Prefer `topic -c` over raw `git worktree add` — it handles username prefixing, remote-branch detection, env-file symlinks, node_modules hardlinking, and post-create setup from `~/.config/topic/topic.toml`.

## Commands

```bash
topic -c <branch>        # Create a new topic worktree (no tmux session).
                         # - Prefixes $USER/ unless <branch> already exists on remote/locally.
                         # - Prints the worktree path on stdout (agents should cd there).
topic <branch>           # Switch into the topic; starts tmux session if interactive.
topic                    # Fuzzy-pick a topic (interactive only).
topic -r [<branch>]      # Remove a topic (confirms on uncommitted changes, cleans bazel cache).
topic -p                 # Purge merged/remote-deleted topics + orphaned bazel caches.
```

## Agent usage pattern

When the user wants you to start work on a branch:

1. Create the worktree and capture its path:

    ```bash
    WT=$(topic -c <branch> | tail -1)
    cd "$WT"
    ```

2. Do the work in `$WT`. Run tests, commits, edits there — not in the original checkout.

3. Do NOT run `tmux` commands from an agent. `topic -c` intentionally skips session creation; the user attaches via `topic <branch>` themselves when they want to drive interactively.

## Branch naming

- Plain names (`quip_poc`, `fix-login`) are auto-prefixed to `$USER/<name>`.
- Fully-qualified names (`jangabrielmylius/foo`, `someone/bar`) are kept as-is.
- If `<branch>` exists on origin, `topic -c` checks it out locally with upstream tracking configured — no prefix added.

## What topic sets up per worktree

Driven by `~/.config/topic/topic.toml`:

- Symlinks env files from `~/.env/` into the worktree
- Hard-link copies `node_modules/` from the main worktree (instant, no reinstall)
- Runs `post_create_commands` (e.g. `make merge-base-hook`) inside the new worktree

## Removing topics

- `topic -r <branch>` — confirms if worktree is dirty, kills tmux session, removes worktree + its bazel output base.
- `topic -p` — removes all worktrees whose upstream branches are merged/deleted, plus orphaned bazel caches. Never touches worktrees with unpushed commits.

## Do NOT

- Do not `git worktree add` directly — skip the env-file, node_modules, and post-create setup.
- Do not start tmux sessions from automation.
- Do not run `topic` against the main worktree path; always work out of the printed topic path.
