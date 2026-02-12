---
description: Enforces running the post-task-reviewer subagent after completing a multi-step implementation plan
globs:
alwaysApply: true
---

# Post-Task Review Requirement

After completing a **multi-step implementation plan** — and before reporting the work as done to the user — you **must** invoke the `post-task-reviewer` subagent to review all changes.

## When to invoke

Invoke the reviewer when ALL of the following are true:
- You executed a plan with 3 or more distinct implementation steps
- You modified or created 2 or more source files
- The changes involve logic, not just config, comments, or formatting

## When NOT to invoke

Skip the reviewer for:
- Single-file edits or quick fixes
- Renaming, formatting, or typo corrections
- Config changes, dependency bumps, or version updates
- Answering questions or exploring code without making changes
- Any task you completed in 1-2 steps

## How to invoke

Use the Task tool to launch the `post-task-reviewer` subagent. Pass it a description of what was implemented so it has context for the review.

## What to do with the results

- If the reviewer finds and fixes issues, include those fixes in your final response
- If the reviewer flags architectural concerns, surface them to the user
- Do not report the task as complete until the review passes
