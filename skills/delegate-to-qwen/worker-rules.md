## How to work

Your **checklist** carries the run. Before editing, write every requirement in the brief as a numbered item, small ones included ("links to X", "in both languages"). The run is finished when every item is marked done, partly done, or not done, each with its proof: a test, command output, or a quoted line of the diff.

1. Work in your current directory, the worktree you were given; run `pwd` first.
2. Read the code around a change before writing it, and follow its patterns, naming, and placement. Reuse data already loaded in scope before adding a query or file read.
3. Give every change in behaviour a test, the hard parts included. When logic is awkward to test in place, move it into a small pure function and test that.
4. Write interface text in every language in the voice of the strings beside it: same person and formality, throughout each string.
5. For a change people see, look at it: render the page and read its text, using the project's page command if its `AGENTS.md` names one. If you cannot, mark the item partly done and say why.
6. Stop only processes you started, by the PID you recorded when starting them.
7. Commit once the project's check passes (its `AGENTS.md` names the command; a pre-commit hook may run it). A failing check means the work is unfinished: fix the cause and commit again. Bypassing a hook with `--no-verify` is off limits.

Final reply: the checklist with proofs, which changes have tests and which do not, and anything you skipped or were unsure about. An honest "not done" beats a wrong "done". Include the commit SHA.
