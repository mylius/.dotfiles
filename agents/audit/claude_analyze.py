#!/usr/bin/env python3
"""Classify Claude Code tool calls and Bash commands by failure type.

Read-only over $WORKSPACE_ROOT/.claude/projects. Writes only under $AUDIT_OUT/claude.
Run through agents-audit, which sets AUDIT_START, AUDIT_END and AUDIT_OUT.
"""
import collections
import glob
import json
import os
import re

ROOT = os.path.join(os.environ.get("WORKSPACE_ROOT") or os.path.expanduser("~"), ".claude/projects")
OUT = os.path.join(os.environ["AUDIT_OUT"], "claude")
START, END = os.environ["AUDIT_START"], os.environ["AUDIT_END"]

SECRET_PATTERNS = [
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "<REDACTED-GH-TOKEN>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "<REDACTED-GH-TOKEN>"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "<REDACTED-KEY>"),
    (re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"), "<REDACTED-SLACK>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<REDACTED-AWS>"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"), "<REDACTED-JWT>"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"), r"\1<REDACTED>"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*\s*[=:]\s*)(\S+)"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(--(?:token|password|api[-_]key|secret)[= ]+)(\S+)"), r"\1<REDACTED>"),
    (re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1<REDACTED>@"),
    (re.compile(r"[\w.+-]+@wayve\.ai"), "<EMAIL>"),
]


def redact(s):
    if s is None:
        return None
    for pat, rep in SECRET_PATTERNS:
        s = pat.sub(rep, s)
    return s


def short(s, n=220):
    s = redact(s or "").replace("\n", " ⏎ ")
    return s if len(s) <= n else s[: n - 3] + "..."


def text_of(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for x in content:
        if isinstance(x, dict):
            if x.get("type") == "text":
                parts.append(x.get("text", ""))
            elif x.get("type") == "tool_reference":
                parts.append("[tool_reference %s]" % x.get("tool_name"))
            else:
                parts.append(json.dumps(x)[:500])
        else:
            parts.append(str(x))
    return "\n".join(parts)


# ---------------------------------------------------------------- loading
def load():
    calls, results = {}, {}
    dup_calls = 0
    files = sorted(glob.glob(ROOT + "/*/**/*.jsonl", recursive=True))
    for p in files:
        rel = os.path.relpath(p, ROOT)
        proj = rel.split("/")[0]
        tag = "subagent" if "/subagents/" in p else "main"
        with open(p, errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                typ = r.get("type")
                ts = r.get("timestamp") or ""
                m = r.get("message") or {}
                c = m.get("content")
                if typ == "assistant" and isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            tid = b.get("id")
                            if tid in calls:
                                dup_calls += 1
                                continue
                            calls[tid] = dict(
                                id=tid, name=b.get("name", ""), input=b.get("input") or {},
                                ts=ts, proj=proj, tag=tag, file=rel,
                            )
                elif typ == "user" and isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            tid = b.get("tool_use_id")
                            if tid in results:
                                continue
                            results[tid] = dict(
                                is_error=bool(b.get("is_error")),
                                text=text_of(b.get("content")),
                            )
    return calls, results, dup_calls, len(files)


# ---------------------------------------------------------------- shell parsing
def strip_heredoc(cmd):
    m = re.search(r"<<-?\s*(['\"]?)(\w+)\1", cmd)
    if not m:
        return cmd
    head = cmd[: m.start()]
    eol = cmd.find("\n", m.end())
    if eol == -1:
        return head + cmd[m.end():]
    tail_same_line = cmd[m.end(): eol]
    term = re.search(r"^\s*" + re.escape(m.group(2)) + r"\s*$", cmd[eol + 1:], re.M)
    after = cmd[eol + 1 + term.end():] if term else ""
    return head + " " + tail_same_line + "\n" + after


def split_top(cmd):
    """Split on unquoted &&, ||, |, ;, newline at paren depth 0.
    Returns list of (segment_text, operator_after or None)."""
    segs, cur = [], []
    i, n, q, depth = 0, len(cmd), None, 0
    while i < n:
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            elif ch == "\\" and q == '"' and i + 1 < n:
                cur.append(cmd[i + 1])
                i += 1
            i += 1
            continue
        if ch in "'\"":
            q = ch
            cur.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            cur.append(ch + cmd[i + 1])
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            if cmd.startswith("&&", i) or cmd.startswith("||", i):
                segs.append(("".join(cur), cmd[i: i + 2]))
                cur = []
                i += 2
                continue
            if ch in "|;\n":
                segs.append(("".join(cur), ch))
                cur = []
                i += 1
                continue
        cur.append(ch)
        i += 1
    segs.append(("".join(cur), None))
    return [(t, op) for t, op in segs if t.strip()]


TRIVIAL = {"cd", "pushd", "popd", "export", "set", "unset", "source", ".", "echo", "printf",
           "sleep", "true", "false", "umask", "wait", "shopt", "alias", "local", "readonly",
           "eval", "exit", "return", "read", "unalias", "trap", "ulimit", "hash", "mkdir",
           "touch", "rm", "chmod", "ln", "for", "while", "until", "do", "done", "if", "then",
           "else", "elif", "fi", "case", "esac", "{", "}", "(", ")", "in", "function"}
TAIL_PROGS = {"head", "tail", "tee", "wc", "sort", "uniq", "cat", "less", "more", "column", "cut", "tr"}
SUB_PROGS = {"git", "gh", "bazel", "bazelisk", "pnpm", "npm", "yarn", "docker", "kubectl", "cargo",
             "go", "make", "uv", "pip", "pip3", "poetry", "apt", "apt-get", "brew", "terraform",
             "aws", "gcloud", "az", "databricks", "systemctl", "dotnet", "mvn", "gradle", "npx", "tox", "nox"}
INTERP = {"python", "python3", "node", "bash", "sh", "zsh", "ruby", "perl"}


def tokenize(seg):
    try:
        import shlex
        toks = shlex.split(seg, posix=True)
    except ValueError:
        toks = seg.split()
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if re.fullmatch(r"\d*(>>?|<)&?\d*|&>>?|\d*>>?|\d*<", t):
            i += 2
            continue
        if re.match(r"^\d*[<>]", t) or t.startswith("&>"):
            i += 1
            continue
        out.append(t)
        i += 1
    return out


SHELL_KEYWORDS = {"do", "then", "else", "if", "while", "until", "{", "(", "!"}


def strip_wrappers(toks):
    changed = True
    while changed and toks:
        changed = False
        while toks and toks[0] in SHELL_KEYWORDS:
            toks = toks[1:]
            changed = True
        if not toks:
            break
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
            toks = toks[1:]
            changed = True
        if not toks:
            break
        b = os.path.basename(toks[0])
        if b == "env":
            toks = toks[1:]
            while toks and (toks[0].startswith("-") or re.match(r"^[A-Za-z_]\w*=", toks[0])):
                toks = toks[2:] if toks[0] in ("-u", "-C", "-S") else toks[1:]
            changed = True
        elif b == "timeout":
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                toks = toks[2:] if toks[0] in ("-s", "-k", "--signal", "--kill-after") else toks[1:]
            if toks:
                toks = toks[1:]
            changed = True
        elif b in ("sudo", "nohup", "time", "nice", "exec", "stdbuf", "caffeinate", "command", "builtin"):
            if b == "command" and len(toks) > 1 and toks[1] in ("-v", "-V"):
                break
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                toks = toks[2:] if toks[0] in ("-u", "-n") else toks[1:]
            changed = True
    return toks


def label_of(toks):
    if not toks:
        return "", ""
    first = toks[0]
    base = os.path.basename(first)
    rest = toks[1:]
    if base == "command" and rest[:1] in (["-v"], ["-V"]):
        return "command -v", "command"
    if base == "[" or base == "[[":
        return base, base
    if base in INTERP:
        if "-c" in rest:
            return f"{base} -c", base
        if "-m" in rest:
            i = rest.index("-m")
            mod = rest[i + 1] if i + 1 < len(rest) else "?"
            return f"{base} -m {mod}", base
        for t in rest:
            if t.startswith("-"):
                continue
            if t in ("-", "<<"):
                break
            if re.search(r"\.(py|js|mjs|ts|sh)$", t):
                return f"{base} {os.path.basename(t)}", base
            break
        return f"{base} (stdin/module)", base
    if base == "git":
        i = 0
        while i < len(rest):
            if rest[i] in ("-C", "-c", "--git-dir", "--work-tree"):
                i += 2
                continue
            if rest[i].startswith("-"):
                i += 1
                continue
            break
        sub = rest[i] if i < len(rest) else ""
        return f"git {sub}".strip(), "git"
    if base == "gh":
        grp = rest[0] if rest else ""
        verb = rest[1] if len(rest) > 1 and not rest[1].startswith("-") else ""
        return f"gh {grp} {verb}".strip(), "gh"
    if base in ("uv", "poetry") and rest[:1] == ["run"]:
        inner = strip_wrappers(rest[1:])
        inner_label, _ = label_of(inner) if inner else ("", "")
        return f"{base} run {inner_label}".strip(), base
    if base in ("npx", "bunx"):
        inner = strip_wrappers(rest)
        inner_label, _ = label_of(inner) if inner else ("", "")
        return f"{base} {inner_label}".strip(), base
    if base in SUB_PROGS:
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 1
        sub = rest[i] if i < len(rest) else ""
        if base in ("pnpm", "npm", "yarn") and sub in ("run", "exec", "dlx") and i + 1 < len(rest):
            return f"{base} {sub} {rest[i + 1]}", base
        if base in ("aws", "gcloud", "az", "databricks", "docker", "kubectl", "terraform") and i + 1 < len(rest) and not rest[i + 1].startswith("-"):
            return f"{base} {sub} {rest[i + 1]}", base
        return f"{base} {sub}".strip(), base
    if first.startswith("./") or first.startswith("/"):
        return "local script " + base, base
    return base, base


def seg_info(text):
    toks = strip_wrappers(tokenize(text))
    label, base = label_of(toks)
    return {"text": text.strip(), "toks": toks, "label": label, "base": base,
            "trivial": (not toks) or base in TRIVIAL}


def parse_pipelines(cmd):
    segs = split_top(strip_heredoc(cmd))
    pipes, cur = [], []
    for text, op in segs:
        cur.append(seg_info(text))
        if op != "|":
            pipes.append(cur)
            cur = []
    if cur:
        pipes.append(cur)
    return pipes




GREP_BASE = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "zgrep"}
TEST_BASE = {"test", "[", "[["}
DIFF_BASE = {"diff", "cmp", "colordiff", "diff3"}
PROBE_BASE = {"which", "type", "pgrep", "hash", "command -v"}
NOISE_OUTPUT_MENTION = {"ls", "cat", "sed", "awk", "head", "tail", "echo", "grep", "rg", "test", "cd",
                        "for", "while", "done", "wc", "sort", "uniq", "tr", "cut", "tee", "find", "xargs"}


def sem_match(s, code, out):
    """True when the program's known exit semantics fit the observed exit code."""
    b, lab = s["base"], s["label"]
    if code is None:
        return False
    if b in GREP_BASE or lab == "git grep":
        return code in (1, 2)
    if b in TEST_BASE or b in DIFF_BASE:
        return code == 1
    if b in PROBE_BASE or lab in PROBE_BASE:
        return code == 1
    if b == "curl":
        return code in (6, 7, 22, 28, 35, 52, 56, 60)
    if b in ("pkill", "kill", "killall"):
        return code in (1, 9, 15, 137, 143, 144)
    if b == "git":
        return code in (1, 128, 129)
    if b in INTERP:
        return code in (1, 2) and "Traceback" in out
    if b == "gh":
        return code in (1, 2, 4, 8)
    if b in ("bazel", "bazelisk"):
        return code in (1, 2, 3, 4)
    if b in ("pytest", "ruff", "mypy", "tsc", "eslint", "pyright", "cargo", "go", "npm", "pnpm", "yarn", "uv"):
        return True
    return False


def attribute(pipes, out_head, code=None):
    """Return (segment, method, confidence) for the segment most plausibly responsible."""
    flat = [s for p in pipes for s in p]
    if not flat:
        return None, "empty", "none"
    m = (re.search(r"command not found: ([\w.\-/]+)", out_head)
         or re.search(r"(?:^|\n)(?:zsh: |bash: )?(?:line \d+: )?([\w.\-/]+): (?:command )?not found", out_head))
    if m:
        name = os.path.basename(m.group(1))
        for s in flat:
            if s["base"] == name:
                return s, "name-match", "high"
    nontriv = [p for p in pipes if any(not s["trivial"] for s in p)]
    if not nontriv:
        return flat[0], "all-trivial", "low"
    # exit-code semantics: a program whose known exit codes fit the observed code
    if code not in (None, 0):
        for p in reversed(nontriv):
            for s in reversed(p):
                if not s["trivial"] and sem_match(s, code, out_head):
                    return s, "exit-semantics", "medium"
    # the program named in the output head
    for p in reversed(nontriv):
        for s in p:
            if (not s["trivial"] and s["base"] and s["base"] not in NOISE_OUTPUT_MENTION
                    and re.search(r"\b%s\b" % re.escape(s["base"]), out_head)):
                return s, "output-mention", "medium"
    if len(nontriv) == 1:
        p = nontriv[0]
        method_base = "only-nontrivial"
        conf = "medium"
    else:
        p = nontriv[-1]
        method_base = "chain-last"
        conf = "low"
    if len(p) > 1:
        last = p[-1]
        if last["trivial"] or last["base"] in TAIL_PROGS:
            nt = [s for s in p if not s["trivial"] and s["base"] not in TAIL_PROGS] or [s for s in p if not s["trivial"]]
            if nt:
                return nt[-1], "pipeline-last-nontail", "low" if conf == "low" else "medium"
        return last, ("pipeline-last" if method_base == "chain-last" else "pipeline-last"), conf
    return p[-1], method_base, conf


# ---------------------------------------------------------------- classification
FAIL_RE = re.compile(r"\b(FAILED|FAILURES?|Failures?|failed|Failed|FAIL:|--- FAIL|\d+ failed|test result: FAILED)\b")
TEST_LABEL = re.compile(r"(^|\s)(pytest|bazel test|go test|cargo test|npm test|pnpm test|yarn test|npm run test|pnpm run test|pnpm run tests?|jest|vitest|mocha|tox|nox|ctest|make test|python3? -m pytest|uv run pytest|poetry run pytest|pnpm vitest|npx vitest|npx jest)(\s|$)")
LINT_LABEL = re.compile(r"(^|\s)(ruff|mypy|pyright|tsc|eslint|flake8|pylint|clippy|golangci-lint|pre-commit|shellcheck|prettier|biome|black|hadolint|yamllint|lint|typecheck|check)(\s|$)")
GREP_PROGS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "zgrep", "git grep"}
DIFF_PROGS = {"diff", "cmp", "colordiff", "diff3"}
TEST_PROGS = {"test", "[", "[["}
PROBE_PROGS = {"which", "type", "pgrep", "hash", "command -v", "kill -0"}

DENY_CLASSIFIER = "Permission for this action was denied by the Claude Code auto mode classifier"


def denial_reason(text):
    m = re.search(r"Reason: \[([^\]]+)\]", text)
    return m.group(1) if m else "unspecified"


def _unused_non_bash_denied(text):
    if DENY_CLASSIFIER in text:
        return "denied", "classifier", denial_reason(text)
    if "doesn't want to proceed" in text or "user rejected" in text.lower():
        return "denied", "user", ""
    if "Claude requested permissions to use" in text:
        return "denied", "permission_system", ""
    if re.search(r"hook (error|blocked)|blocked by (a )?hook|PreToolUse", text):
        return "denied", "hook", ""
    if "interrupted by user" in text.lower() or "request interrupted" in text.lower():
        return "interrupted", "user", ""
    return None


def classify_bash(seg_text, seg, method, conf, text, is_error, pipes_for_kill=()):
    """Return (category, subcategory, cluster, code). Category in
    ok, expected_nonzero, real_failure, denied, interrupted, tool_misuse, no_result."""
    t = text.lstrip()
    m = re.match(r"Exit code (\d+)", t)
    code = int(m.group(1)) if m else None
    body = t[m.end():].lstrip("\n") if m else t
    label = seg["label"] if seg else ""
    base = seg["base"] if seg else ""
    head = t[:400]
    # tool-level outcomes: only when the harness reports an error and no exit code
    if is_error and code is None:
        if DENY_CLASSIFIER in head:
            return "denied", "classifier", denial_reason(head), None
        if "denied by a built-in Claude Code safety check" in head:
            return "denied", "builtin_safety_check", "built-in removal safety check", None
        if "Permission for this command was denied" in head or "doesn't want to proceed" in head:
            return "denied", "user", "", None
        if "Blocked: sleep" in head:
            return "denied", "harness", "harness sleep block", None
        if re.search(r"hook (error|blocked)|blocked by (a )?hook", head):
            return "denied", "hook", "hook error/block", None
        if "interrupted by user" in head.lower() or "<error>Command was aborted" in head:
            return "interrupted", "user_or_abort", "command aborted/interrupted", None
        if "session ended before this call" in head:
            return "no_result", "", "session ended before result recorded", None
        if "No such tool available" in head or "InputValidationError" in head:
            return "real_failure", "tool_misuse", "tool misuse: unknown tool / input validation", None
        if "Working directory" in head and "was deleted" in head:
            return "real_failure", "tool-level", "wrong cwd: working directory deleted", None
        return "real_failure", "tool-level", "tool-level: " + short(head, 70), None
    if code is None:
        return "ok", "", "", None
    if code == 0:
        return "ok", "", "", 0
    # nonzero exit from a command that ran
    if code in (137, 143, 144, 9) and any(
            s_["base"] in ("pkill", "killall", "kill") for p_ in pipes_for_kill for s_ in p_):
        return "real_failure", "self_kill", "killed by pkill/kill (exit %d)" % code, code
    if re.search(r"refusing to run", body[:300]):
        return "real_failure", "guard", "pkill refused by guard (matches Claude CLI)", code
    # explicit error text always wins over an expected-exit label
    error_text = re.search(r"bad pattern|parse error|no matches found|command not found|No such file|"
                           r"Traceback|fatal:|Permission denied|syntax error|unmatched|refusing to run", body[:3000])
    # low-confidence attribution (position only) cannot justify an expected-exit label
    if conf != "low" and method not in ("name-match",) and not error_text:
        if (base in GREP_PROGS or label in GREP_PROGS or base in GREP_BASE) and code == 1 and not body.strip().startswith("grep:"):
            return "expected_nonzero", "no_match", "grep/rg no match (exit 1)", code
        if base in DIFF_BASE and code == 1:
            return "expected_nonzero", "diff_differs", "diff/cmp differs", code
        if base in TEST_BASE and code == 1:
            return "expected_nonzero", "test_condition_false", "test/[ false", code
        if (base in PROBE_BASE or label in PROBE_BASE) and code == 1:
            return "expected_nonzero", "probe_negative", "probe negative (which/type/pgrep)", code
        if label.startswith("git ") and code == 1 and re.search(
                r"git (diff .*(--quiet|--exit-code)|check-ignore|merge-base|show-ref|config|rev-parse --verify|ls-files)", seg_text):
            return "expected_nonzero", "probe_negative", "git probe negative", code
        if re.search(r"\bkill -0\b", seg_text) and code == 1:
            return "expected_nonzero", "probe_negative", "kill -0 probe", code
        if label.startswith("gh pr checks") and code == 8:
            return "expected_nonzero", "tool_findings", "gh pr checks reported failing checks", code
        if TEST_LABEL.search(label) and "Build did NOT complete" not in body and not re.search(r"^ERROR: .*BUILD", body, re.M):
            if (code == 3 and label.startswith("bazel test")) or FAIL_RE.search(body):
                return "expected_nonzero", "tool_findings", "test runner reported failing tests", code
        if LINT_LABEL.search(label) and code in (1, 2) and "Traceback" not in body and code != 127:
            if not re.search(r"command not found|No such file", body[:300]):
                return "expected_nonzero", "tool_findings", "linter/typechecker reported findings", code
    if base == "curl" and code is not None:
        names = {6: "DNS failure", 7: "connection refused", 28: "timeout", 35: "TLS handshake error",
                 60: "TLS certificate error", 22: "HTTP error status (-f)", 52: "empty reply", 56: "connection reset"}
        return "real_failure", "", "network: curl %s (exit %d)" % (names.get(code, "error"), code), code
    if base in GREP_BASE and code == 2 and not re.search(r"No such file|Permission denied", body[:300]):
        return "real_failure", "", "grep/rg exit 2, no message captured (missing path or bad regex likely)", code
    if base in ("ls", "sed", "cat") and code == 2:
        return "real_failure", "", "file/path not found (%s exit 2, no message captured)" % base, code
    if code == 128 and label.startswith("git"):
        return "real_failure", "", "git: fatal (exit 128, no message captured)", code
    cl = cluster_real(code, body, label)
    if cl.startswith("unclassified"):
        cl = "unexplained nonzero exit, no error text (%s)" % ("exit 1" if code == 1 else "exit %d" % code)
    return "real_failure", "", cl, code


REAL_CLUSTERS = [
    ("zsh glob: no matches found", r"no matches found"),
    ("shell env: _load_nvm missing (nvm lazy loader)", r"command not found: _load_nvm"),
    ("command not found", r"command not found|not recognized as an internal|: not found\b"),
    ("python import error", r"Traceback[\s\S]*(ModuleNotFoundError|ImportError|No module named)"),
    ("python syntax error", r"Traceback[\s\S]*SyntaxError|^\s*SyntaxError"),
    ("python exception (other)", r"Traceback \(most recent call last\)"),
    ("shell quoting/syntax error", r"parse error near|unexpected EOF|unmatched|bad substitution|syntax error|unterminated|Unterminated|event not found|bad pattern"),
    ("wrong cwd / not a git repo", r"Not a git repository|not a git repository"),
    ("permission / sandbox", r"Permission denied|EACCES|Operation not permitted|sandbox|bwrap|apparmor|AppArmor|Read-only file system"),
    ("auth / credentials", r"HTTP/[\d.]+ 40[13]|(HTTP|status|code) 40[13]\b|40[13] Unauthorized|40[13] Forbidden|Unauthorized|not logged in|gh auth login|Bad credentials|[Aa]uthentication (failed|required)|invalid_grant|Could not read Username|credentials? (not found|missing|invalid)"),
    ("network", r"Could not resolve host|Connection refused|ECONNREFUSED|Name or service not known|Temporary failure in name resolution|Network is unreachable|ETIMEDOUT|Failed to connect|Connection reset"),
    ("file/path not found", r"No such file or directory|does not exist|ENOENT|cannot access|File does not exist|no such file"),
    ("CLI flag / usage misuse", r"[Uu]sage:|unrecognized option|unknown option|invalid option|unknown flag|flag provided but not defined|requires an argument|illegal option|unknown command|Unknown command"),
    ("git: push rejected", r"rejected|non-fast-forward|\(fetch first\)"),
    ("git: merge/rebase conflict", r"CONFLICT|Merge conflict|could not apply|Automatic merge failed|needs merge"),
    ("git: pathspec/revision not found", r"pathspec .* did not match|unknown revision|bad revision|ambiguous argument|invalid reference"),
    ("git: dirty tree blocks op", r"would be overwritten|Your local changes|commit or stash|untracked working tree files would"),
    ("git: other fatal", r"fatal:"),
    ("bazel: build/analysis error", r"Build did NOT complete|Analysis failed|no such target|no such package|Unknown label|Target .* failed to build|BUILD file"),
    ("compile/type error (code under work)", r"error\[E|error: |\berror TS\d+|compilation (failed|terminated)|Compilation failed|Build failed|\bFAILED\b"),
    ("timeout", r"timed out|Timeout \d+ms exceeded|timeout exceeded|ETIMEDOUT"),
    ("json/jq parse error", r"jq: error|parse error: |JSONDecodeError|Expecting value"),
    ("node/npm/pnpm error", r"npm ERR|ERR_PNPM|ERR!|node:internal|TypeError|ReferenceError"),
    ("gcloud/az/aws/databricks CLI error", r"ERROR: \(gcloud|An error occurred|databricks: error|AuthorizationError|InvalidClientTokenId"),
]


def cluster_real(code, body, label):
    if code in (124,):
        return "timeout"
    if code in (137, 143, 144, 9):
        return "killed (exit %d)" % code
    for name, pat in REAL_CLUSTERS:
        if re.search(pat, body[:4000]):
            return name
    if code == 127:
        return "command not found"
    if code == 126:
        return "permission / sandbox"
    if not body.strip():
        return "unclassified (exit %d, no output)" % code
    return "unclassified (exit %d)" % code


def classify_nonbash(name, text, is_error):
    if not is_error:
        return "ok", "", ""
    head = text[:400]
    if DENY_CLASSIFIER in head:
        return "denied", "classifier", denial_reason(head)
    if "Claude requested permissions to use" in head:
        return "denied", "permission_system", "MCP permission not granted"
    if "doesn't want to proceed" in head or "The user doesn't want" in head:
        return "denied", "user", ""
    if re.search(r"hook (error|blocked)|blocked by (a )?hook", head):
        return "denied", "hook", ""
    if "interrupted by user" in head.lower():
        return "interrupted", "user", ""
    rules = [
        ("File has not been read yet", "file not read first"),
        ("has been modified since read", "stale read (modified since read)"),
        ("File does not exist", "file not found"),
        ("Operation not permitted", "permission / sandbox"),
        ("EACCES", "permission / sandbox"),
        ("blocks the sandbox", "sandbox host blocked"),
        ("No preview automation host", "no preview host"),
        ("No active preview tab", "no preview host"),
        ("InputValidationError", "input validation (schema)"),
        ("validating \"arguments\"", "MCP argument validation"),
        ("No such tool available", "unknown tool name"),
        ("Error executing tool", "MCP backend error"),
        ("capability_denied", "capability denied"),
        ("The operation timed out", "timeout"),
        ("Invalid argument", "invalid argument"),
        ("Failed to create issue", "backend rejected request"),
        ("old_string", "edit old_string not found"),
    ]
    for pat, cl in rules:
        if pat in text[:600]:
            sub = "tool_misuse" if cl in ("input validation (schema)", "MCP argument validation", "unknown tool name") else ""
            return "real_failure", sub, cl
    return "real_failure", "", "other tool error: " + short(text, 60)


def mcp_server(name):
    if name.startswith("mcp__"):
        parts = name.split("__")
        return parts[1] if len(parts) > 2 else name
    return ""


def main():
    calls, results, dup_calls, nfiles = load()
    stats = collections.Counter()
    stats["files"] = nfiles
    stats["duplicate_tool_use_ids_skipped"] = dup_calls
    rows = []
    for tid, c in calls.items():
        day = c["ts"][:10]
        if not (START <= day <= END):
            stats["excluded_out_of_window"] += 1
            continue
        res = results.get(tid)
        name = c["name"]
        row = {"id": tid, "tool": name, "server": mcp_server(name), "ts": c["ts"], "tag": c["tag"],
               "project": c["proj"], "file": c["file"]}
        if name == "Bash":
            cmd = c["input"].get("command", "") or ""
            pipes = parse_pipelines(cmd)
            out_text = res["text"] if res is not None else ""
            m = re.match(r"\s*Exit code (\d+)", out_text)
            code = int(m.group(1)) if m else None
            seg, method, conf = attribute(pipes, out_text[:600], code)
            seg_label = seg["label"] if seg else "(empty)"
            test_like = any(TEST_LABEL.search(x["label"] or "") for p_ in pipes for x in p_)
            masked_fail = bool(test_like and code in (None, 0) and re.search(
                r"Build completed, [^\n]*\bFAILED\b|^FAIL: //|^\s*=+ .*\b[1-9]\d* failed\b.* =+$|"
                r"^\s*Tests\s+[1-9]\d* failed|test result: FAILED|^//\S+\s+FAILED in \d", out_text, re.M))
            row.update(label=seg_label, method=method, confidence=conf, exit=code, masked_test_failure=masked_fail,
                       test_like=test_like, piped=("|" in cmd),
                       full_command=redact(cmd), output_head=short(out_text, 400),
                       is_error=(res["is_error"] if res else None), segments=len(seg_text_list(pipes)))
            if res is None:
                row.update(category="no_result", subcat="", cluster="no result recorded")
            else:
                cat, sub, cl, _ = classify_bash(cmd, seg, method, conf, out_text, res["is_error"], pipes)
                row.update(category=cat, subcat=sub, cluster=cl)
        else:
            if res is None:
                row.update(category="no_result", subcat="", cluster="no result recorded", label=name,
                           method="", confidence="", exit=None, full_command=redact(json.dumps(c["input"])[:2000]),
                           output_head="", is_error=None)
            else:
                cat, sub, cl = classify_nonbash(name, res["text"], res["is_error"])
                row.update(category=cat, subcat=sub, cluster=cl, label=name, method="", confidence="",
                           exit=None, full_command=redact(json.dumps(c["input"])[:2000]),
                           output_head=short(res["text"], 400), is_error=res["is_error"])
        rows.append(row)
    stats["rows_in_window"] = len(rows)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "calls_classified.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    with open(os.path.join(OUT, "stats.json"), "w") as fh:
        json.dump(stats, fh, indent=2)
    print(json.dumps(stats, indent=2))


def seg_text_list(pipes):
    return [s for p in pipes for s in p]


if __name__ == "__main__":
    main()
