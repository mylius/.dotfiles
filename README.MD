# .dotfiles

Shared across the private and work MacBooks and the private and work Linux boxes.

## Install

```sh
git clone git@github.com:mylius/.dotfiles.git ~/.dotfiles
~/.dotfiles/setup --profile private   # or --profile work
```

`setup` picks stow packages by OS and profile, links them, renders the agent
instruction files, and installs an hourly `dotfiles-sync` timer (launchd on
macOS, a systemd user timer or cron on Linux) that pulls `main` and re-runs
`setup`. The profile is stored in `~/.config/dotfiles/profile`.

## Layout

- One stow package per tool, laid out relative to `$HOME` (`zsh/.zshrc`,
  `ghostty/.config/ghostty/config`).
- `env/.config/env` is sourced by every shell and script. It sets
  `WORKSPACE_ROOT` to `/workspace` on work Linux boxes that have it, else
  `$HOME`, and sets the XDG and agent home directories only when the workspace
  is separate.
- Files ending in `.tmpl` are rendered by `install` with `@WORKSPACE_ROOT@`,
  `@HOME@`, `@DOTFILES@`, and `@DOTFILES_PROFILE@` replaced; the rendered file
  is gitignored and linked.
- `env-work/` holds Linux work-only files (systemd `environment.d`).

## Agents and skills

`agents-sync` renders `~/.claude/CLAUDE.md` and `$CODEX_HOME/AGENTS.md` from:

| file | when |
| --- | --- |
| `agents/common.md` | always |
| `agents/host-mac.md` or `agents/host-linux.md` | by OS |
| `agents/private.md` | profile `private` |
| `~/.dotfiles-work/agents/work.md` | profile `work` |
| `agents/local.md` | this machine only, gitignored |

`private`, `work`, and `local` may each have a `-claude.md` and `-codex.md`
sibling that only that tool receives. Bullets starting with `- Claude` or
`- Codex` go only to that agent.

Skills: `skills/` is linked into `~/.agents/skills` everywhere,
`skills-private/` on private machines, and `~/.dotfiles-work/skills/` on work
machines. `agents-skills-sync` also installs the npm-distributed skills.

## The work repo

Work material never goes in this public repo. Clone the private
`dotfiles-work` repo to `~/.dotfiles-work` on work machines with:

```
agents/work.md        work rules, appended after the host file
agents/slow-commands  regexes for the codex-wait-guard hook
agents/bin/           work-only tools, linked into the workspace bin dir
agents/sync.d/        executables run by agents-sync with the bin dir as $1
skills/               work-only skills
```

`dotfiles-sync` pulls it alongside this repo.
