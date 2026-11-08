---
name: delegate-to-qwen
description: Delegate implementation to the local Qwen model through T3 and Pi, then review its work. Use when the user asks to hand coding work to Qwen or the local model.
---

# Delegate to Qwen

Qwen (`local/qwen3.6-35b-a3b-mtp`, a 35B mixture-of-experts with about 3B active) does well on a tight brief and drifts on a loose one. You own the brief and the review; Qwen owns the edits.

## 1. Check the session

Run `orchestrator_capabilities` once. Qwen needs `runtimeMode: "full-access"` to run commands without a prompt per command, and a child can't have wider access than its parent. Done when this session is in full access; if it isn't, ask the user to switch, since Pi has no `auto` mode and every command would otherwise wait for approval. T3's Pi launch arguments should include `-e ~/.dotfiles/agents/pi/auto-mode/index.ts`, which reviews each of Qwen's commands (rules first, then Haiku) and blocks what is unsafe.

## 2. Pick the starting commit

The child's worktree starts at the parent checkout's `HEAD`. To start elsewhere (a branch with checks not yet on `main`, or a fixed base for comparing runs), make the brief's first command `git reset --hard <sha>`. Done when you can name the commit each child starts from.

## 3. Write the brief

- The task, the files it may touch, and how to tell it is done. Give exact queries, paths, and existing patterns to copy when you know them.
- Plain descriptive headings. Qwen copies labels such as "Task A" into code comments.
- Run independent tasks in parallel only when their file sets don't overlap.
- Append [worker-rules.md](worker-rules.md) verbatim as the last section.

Done when every requirement is written down and each child's file set is disjoint from the others'.

## 4. Launch

`delegate_task` with `target: { providerInstanceId: "pi", model: "local/qwen3.6-35b-a3b-mtp", options: { thinking: "medium" } }`, `isolation: "worktree"`, `runtimeMode: "full-access"`, `role: "implementation"`. Then end the turn; completion wakes you.

A question from the child also wakes you. When auto mode can't reach its reviewer, it asks "Auto mode can't review this command" with Retry and Block. Read it with `t3_pending_request`, tell the user what it says (usually: run `pi`, then `/login`, and pick the named provider), and once they confirm, answer Retry with `t3_pending_request respond`. Pi re-reads its login file, so the child needs no restart.

## 5. Review

Qwen's report says "done" more readily than the diff does. For each child:

- Find its worktree with `git worktree list` and the commit SHA it reports. Read the full diff against the brief, item by item.
- Re-run the project's check there yourself (the command its `AGENTS.md` names).
- Look at every page it changed, rendered, in each interface language.
- Read the auto-mode log (`~/.local/state/pi-auto-mode.jsonl`) for what was blocked and why.
- Read its session log in `~/.pi/agent/sessions/` (the folder named after its worktree path) for check failures it fixed, `--no-verify`, and processes it stopped with `pkill` or `kill`.

Done when every brief requirement is confirmed by your own check, not by Qwen's report.

## 6. Report and keep the lesson

Report what each child got right and wrong, with file and line. Fix small findings yourself in a separate commit so Qwen's commit stays as written. When a mistake recurs across runs, prefer a mechanical check in the project (a pre-commit hook or check script) over a new line in [worker-rules.md](worker-rules.md); add a rule only for what no check can catch, and keep the file short, since Qwen drops rules as the list grows.
