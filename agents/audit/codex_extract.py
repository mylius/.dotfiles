#!/usr/bin/env python3
"""Extract per-call outcomes from Codex rollouts (read-only).

Writes $AUDIT_OUT/codex/data/units.jsonl, one record per
attributable or unattributable tool call (shell and non-shell), plus one
record per code-mode cell (the exec JS wrapper).

Run through agents-audit, which sets AUDIT_START, AUDIT_END and AUDIT_OUT.
"""
import glob
import json
import os
import re
import shlex
import collections

ROOT = os.path.join(os.environ.get("WORKSPACE_ROOT") or os.path.expanduser("~"), ".codex/sessions")
OUT_DIR = os.path.join(os.environ["AUDIT_OUT"], "codex", "data")
OUT = os.path.join(OUT_DIR, "units.jsonl")
WIN_LO, WIN_HI = os.environ["AUDIT_START"], os.environ["AUDIT_END"]

# ---------------------------------------------------------------- JS parsing
class JSErr(Exception):
    pass


UNRES = "UNRESOLVED"


def skip_quoted(s, i):
    """s[i] is a quote char. Return index just past the closing quote."""
    q = s[i]
    i += 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if q == "`" and c == "$" and i + 1 < len(s) and s[i + 1] == "{":
            i = skip_code(s, i + 2, "}")
            continue
        if c == q:
            return i + 1
        i += 1
    return len(s)


def skip_code(s, i, closer):
    """Skip JS code from i until the unmatched closer. Return index after closer."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c in "\"'`":
            i = skip_quoted(s, i)
            continue
        if c == "/" and s[i + 1:i + 2] == "/":
            j = s.find("\n", i)
            i = len(s) if j < 0 else j
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0 and c == closer:
                return i + 1
            depth -= 1
        i += 1
    return len(s)


class JSLit:
    """Tiny parser for JS object/array/string literals used as tool arguments."""

    ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}

    def __init__(self, s):
        self.s = s
        self.i = 0

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n,":
                if c == ",":
                    break
                self.i += 1
            elif s.startswith("//", self.i):
                j = s.find("\n", self.i)
                self.i = len(s) if j < 0 else j
            elif s.startswith("/*", self.i):
                j = s.find("*/", self.i)
                self.i = len(s) if j < 0 else j + 2
            else:
                break

    def string(self):
        s = self.s
        q = s[self.i]
        self.i += 1
        out = []
        while self.i < len(s):
            c = s[self.i]
            if c == "\\":
                n = s[self.i + 1]
                if n in self.ESC:
                    out.append(self.ESC[n])
                    self.i += 2
                elif n == "x":
                    out.append(chr(int(s[self.i + 2:self.i + 4], 16)))
                    self.i += 4
                elif n == "u" and s[self.i + 2:self.i + 3] == "{":
                    j = s.index("}", self.i)
                    out.append(chr(int(s[self.i + 3:j], 16)))
                    self.i = j + 1
                elif n == "u":
                    out.append(chr(int(s[self.i + 2:self.i + 6], 16)))
                    self.i += 6
                elif n == "\n":
                    self.i += 2
                else:
                    out.append(n)
                    self.i += 2
                continue
            if c == q:
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        raise JSErr("unterminated string")

    def template(self):
        s = self.s
        end = skip_quoted(s, self.i)
        raw = s[self.i + 1:end - 1]
        self.i = end
        return ("TEMPLATE", raw)

    def expr_until_delim(self):
        s = self.s
        start = self.i
        depth = 0
        while self.i < len(s):
            c = s[self.i]
            if c in "\"'`":
                self.i = skip_quoted(s, self.i)
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif c == "," and depth == 0:
                break
            self.i += 1
        return (UNRES, s[start:self.i].strip())

    def value(self):
        self.ws()
        s = self.s
        if self.i >= len(s):
            raise JSErr("eof")
        c = s[self.i]
        if c == "{":
            self.i += 1
            obj = {}
            while True:
                self.ws()
                if self.i >= len(s):
                    raise JSErr("eof in object")
                if s[self.i] == "}":
                    self.i += 1
                    return obj
                if s[self.i] in "\"'":
                    key = self.string()
                elif s[self.i] == "[":
                    self.i += 1
                    kv = self.value()
                    key = str(kv[1]) if isinstance(kv, tuple) else str(kv)
                    self.ws()
                    if s[self.i] != "]":
                        raise JSErr("computed key")
                    self.i += 1
                else:
                    m = re.match(r"[A-Za-z_$][\w$]*", s[self.i:])
                    if not m:
                        raise JSErr("bad key at %d" % self.i)
                    key = m.group(0)
                    self.i += len(key)
                self.ws()
                if s[self.i:self.i + 3] == "...":
                    raise JSErr("spread")
                if s[self.i] == ":":
                    self.i += 1
                    obj[key] = self.value()
                else:
                    obj[key] = (UNRES, key)  # shorthand property
                self.ws()
                if self.i < len(s) and s[self.i] == "}":
                    continue
                if self.i < len(s) and s[self.i] == ",":
                    self.i += 1
                    continue
                raise JSErr("expected , or } at %d" % self.i)
        if c == "[":
            self.i += 1
            arr = []
            while True:
                self.ws()
                if self.i >= len(s):
                    raise JSErr("eof in array")
                if s[self.i] == "]":
                    self.i += 1
                    return arr
                arr.append(self.value())
                self.ws()
                if self.i < len(s) and s[self.i] == ",":
                    self.i += 1
        if c in "\"'":
            return self.string()
        if c == "`":
            return self.template()
        m = re.match(r"-?\d+(\.\d+)?", s[self.i:])
        if m:
            self.i += len(m.group(0))
            return float(m.group(0))
        m = re.match(r"(true|false|null|undefined)\b", s[self.i:])
        if m:
            self.i += len(m.group(0))
            return {"true": True, "false": False}.get(m.group(0))
        return self.expr_until_delim()


def parse_inner(js):
    """Return list of (tool, args) for every tools.X( call in a JS block.

    args is a dict when the argument literal parsed, else None.
    Calls that sit inside a template or string are still picked up; that is
    accepted as a minor approximation.
    """
    calls = []
    for m in re.finditer(r"\btools\.(\w+)\s*\(", js):
        tool = m.group(1)
        start = m.end()
        end = skip_code(js, start, ")")
        argtext = js[start:end - 1]
        args = None
        try:
            p = JSLit(argtext)
            v = p.value()
            p.ws()
            if isinstance(v, dict):
                args = v
            elif v is None and argtext.strip() == "":
                args = {}
        except (JSErr, ValueError, IndexError):
            args = None
        calls.append((tool, args, argtext[:200]))
    return calls


TEXT_FAIL_RE = re.compile(r"\bfatal: |command not found|: not found|No such file or directory|Traceback \(most recent|Read-only file system|bwrap:|ERROR: |Permission denied|error: ")
LOOP_RE = re.compile(r"\.map\(|\.forEach\(|\bfor\s*\(|\bwhile\s*\(|\.reduce\(|\.filter\(|\.flatMap\(")
NON_RESULT_TOOLS = {"update_plan", "view_image"}

# ---------------------------------------------------------- command handling
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=('[^']*'|\"[^\"]*\"|\S*)\s+")


def split_ops(cmd):
    """Split on && || ; | and newlines outside quotes. Returns [(op, text)]."""
    heredoc = "<<" in cmd
    out, buf, op = [], [], None
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in "\"'`":
            j = skip_quoted(cmd, i)
            buf.append(cmd[i:j])
            i = j
            continue
        two = cmd[i:i + 2]
        nxt = None
        if two in ("&&", "||"):
            nxt, step = two, 2
        elif c in ";|":
            nxt, step = c, 1
        elif c == "\n" and not heredoc:
            nxt, step = ";", 1
        if nxt is not None and not (nxt == "|" and cmd[i:i + 2] == "|&"):
            out.append((op, "".join(buf).strip()))
            buf = []
            op = nxt
            i += step
            continue
        buf.append(c)
        i += 1
    out.append((op, "".join(buf).strip()))
    return [(o, t) for o, t in out if t]


def strip_wrappers(s):
    prev = None
    while s != prev:
        prev = s
        s = s.strip()
        s = ENV_ASSIGN.sub("", s)
        m = re.match(r"env\s+((-u\s+\S+|-C\s+\S+|-i|-\S+)\s+)*", s)
        if m and s.startswith("env "):
            s = s[m.end():]
        m = re.match(r"timeout\s+(-\S+\s+)*\S+\s+", s)
        if m and s.startswith("timeout "):
            s = s[m.end():]
        m = re.match(r"(sudo|nohup|time|exec|builtin)\s+(-\w+\s+)*", s)
        if m:
            s = s[m.end():]
        if s.startswith("! "):
            s = s[2:]
    return s


def normalize_cmd(cmd, depth=0):
    """Return list of segments dicts {prog, sub, op, text}. [] if nothing."""
    if cmd is None or cmd == UNRES:
        return None
    segs = []
    for op, text in split_ops(cmd):
        t = strip_wrappers(text)
        m = re.match(r"^(?:/\S*/)?(?:ba|z|da)?sh\s+-\w*c\s+(.*)$", t, re.S)
        if m and depth < 3:
            inner = m.group(1).strip()
            if inner[:1] in "\"'":
                try:
                    inner = shlex.split(inner)[0]
                except ValueError:
                    inner = inner[1:-1]
            sub = normalize_cmd(inner, depth + 1)
            if sub:
                segs.extend(sub)
            continue
        if re.match(r"^(cd|pushd|popd)\b", t):
            continue
        try:
            toks = shlex.split(t, posix=True)
        except ValueError:
            toks = t.split()
        if not toks:
            continue
        prog = os.path.basename(toks[0].lstrip("(").rstrip(")"))
        if prog in ("if", "then", "do", "else", "{", "}", "fi", "done", "for", "while"):
            continue
        rest = toks[1:]
        segs.append({"prog": prog, "sub": subcmd(prog, rest, t), "op": op, "text": text})
    return segs


def subcmd(prog, toks, raw):
    def first_nonflag(ts, skip_pairs=()):
        i = 0
        while i < len(ts):
            t = ts[i]
            if t in skip_pairs:
                i += 2
                continue
            if t.startswith("-"):
                i += 1
                continue
            return t
        return ""

    if prog == "git":
        return first_nonflag(toks, ("-C", "-c", "--git-dir", "--work-tree"))
    if prog in ("bazel", "bazelisk"):
        return first_nonflag(toks)
    if prog == "gh":
        return first_nonflag(toks)
    if prog in ("npm", "pnpm", "yarn"):
        s = first_nonflag(toks)
        if s == "run":
            rest = [t for t in toks[toks.index("run") + 1:] if not t.startswith("-")]
            return "run " + (rest[0] if rest else "")
        return s
    if prog in ("kubectl", "cargo", "uv", "pip", "pip3", "poetry", "docker", "terraform",
                "helm", "az", "aws", "gcloud", "go", "dotnet", "codex", "docker-compose"):
        return first_nonflag(toks)
    if prog.startswith("python"):
        if toks[:1] == ["-m"] and len(toks) > 1:
            return "-m " + toks[1]
        if toks[:1] == ["-c"]:
            return "-c"
        if toks[:1] == ["-"] or "<<" in raw:
            return "stdin"
        if toks and toks[0].endswith(".py"):
            return "script"
        return ""
    if prog == "make":
        for t in toks:
            if not t.startswith("-") and "=" not in t:
                return t
        return ""
    return ""


def seg_key(seg):
    return (seg["prog"] + " " + seg["sub"]).strip()


def attribute_segment(segs, out):
    """Pick the segment most plausibly responsible for a failure."""
    if not segs:
        return None, "none"
    if len(segs) == 1:
        return segs[0], "single"
    head = out[:1500]
    m = re.search(r"(?:command not found|not found)[:\s]+([\w.\-]+)|([\w.\-]+): (?:command )?not found", head)
    if m:
        name = m.group(1) or m.group(2)
        for s in segs:
            if s["prog"] == name:
                return s, "cmd-not-found"
    for m in re.finditer(r"^(\S+?): (.*)$", head, re.M):
        if "RIPGREP_CONFIG_PATH" in m.group(0):
            continue  # ripgrep config warning, not an error from the failing command
        for s in segs:
            if s["prog"] == m.group(1):
                return s, "error-prefix"
    for s in segs:
        if re.search(r"\b" + re.escape(s["prog"]) + r"\b", head):
            return s, "word-match"
    return segs[-1], "default-last"


# -------------------------------------------------------- outcome classifiers
CONFLICT_RE = re.compile(r"CONFLICT \(|Automatic merge failed|could not apply [0-9a-f]{6,}|needs merge|fix conflicts|Resolve all conflicts")
USER_RE = re.compile(r"rejected by (the )?user|user (denied|declined|rejected)|approval (was )?(denied|declined)|escalation (request )?(was )?(denied|rejected)|not approved by|declined by (the )?user|aborted by user", re.I)
SANDBOX_RE = re.compile(r"bwrap|fs sandbox|sandbox helper|Read-only file system|blocked by (the )?sandbox|sandbox (denied|blocked|restriction)", re.I)
NETWORK_RE = re.compile(r"error connecting to |check your internet connection|Could not resolve host|Temporary failure in name resolution|Name or service not known|Network is unreachable|No route to host|failed to lookup address|getaddrinfo (ENOTFOUND|EAI_AGAIN)|nodename nor servname provided", re.I)
TEST_RUNNER_RE = re.compile(r"(^|/)(pytest|jest|vitest|tox)$")
TEST_FAIL_RE = re.compile(r"\bFAILED\b|\bfailed\b|\bFailures?\b|\bFAIL:|\d+ failed|tests? failed|AssertionError")
BUILD_ERR_RE = re.compile(r"Build did NOT complete|Analysis failed|ModuleNotFoundError|ImportError|SyntaxError|errors? during collection|error while loading|No such target|no such package|ERROR: /")

CLUSTERS = [
    ("not-git-repo", re.compile(r"not a git repository", re.I)),
    ("cmd-not-found", re.compile(r"command not found|executable file not found|is not recognized as an internal|No such command|unknown command \"|[\w.\-]+: not found")),
    ("zsh-glob", re.compile(r"no matches found|bad pattern")),
    ("shell-syntax", re.compile(r"unexpected EOF|unterminated|syntax error near|parse error near|event not found|bad substitution|unmatched [\"'`(]|unexpected token|missing end of string")),
    ("apply-patch-context", re.compile(r"apply_patch verification failed|Failed to find expected lines|Failed to read file to update")),
    ("path-not-found", re.compile(r"No such file or directory|cannot access|does not exist|ENOENT|cannot stat|Not a directory|Is a directory|no such file", re.I)),
    ("auth", re.compile(r"returned error: 40[13]\b|HTTP[ /0-9.]*40[13]|\b40[13] (Unauthorized|Forbidden)|Unauthorized|Forbidden|Bad credentials|authentication (failed|required)|invalid_auth|not logged in|gh auth login|Permission denied \(publickey\)|token (expired|invalid)|login required|Error code: INVALID_ARGUMENT", re.I)),
    ("json-error", re.compile(r'^\{"error":', re.M)),
    ("wrong-cwd", re.compile(r"not_git_worktree|not a git work ?tree|not a git repository|outside (of )?a git")),
    ("regex-error", re.compile(r"regex parse error|invalid regular expression|Unmatched \(|grep: Unmatched")),
    ("kubectl-error", re.compile(r"Error from server|is not valid for pod|BadRequest")),
    ("kubectl-context", re.compile(r"current-context is not set|context .* does not exist|Unable to connect to the server|no configuration has been provided|The connection to the server")),
    ("gh-error", re.compile(r"^gh: |GraphQL: |Could not resolve to a|HTTP 40\d|HTTP 50\d|no pull requests found|could not find any pull requests", re.M)),
    ("git-apply", re.compile(r"error: patch failed|does not apply|corrupt patch|No valid patches in input")),
    ("git-error", re.compile(r"fatal: |error: pathspec|couldn't find remote ref|src refspec|non-fast-forward|would be overwritten|unknown revision|ambiguous argument|is not a commit|does not point to a commit|error: failed to push|\(fetch first\)")),
    ("python-exception", re.compile(r"Traceback \(most recent call last\)|ModuleNotFoundError|No module named|ImportError|SyntaxError|NameError|TypeError|AttributeError|KeyError|ValueError|AssertionError|IndexError|RuntimeError")),
    ("js-ts-error", re.compile(r"npm ERR!|ERR_PNPM|Cannot find module|TS\d{4}:|ReferenceError|Unexpected token|Cannot read propert|is not a function|pnpm: ")),
    ("timeout", re.compile(r"timed out|Timed out|timeout exceeded|deadline exceeded|\bTimeout\b")),
    ("permission", re.compile(r"Permission denied|Operation not permitted|EACCES")),
    ("resource", re.compile(r"No space left|out of memory|Cannot allocate memory|\bKilled\b|\bOOM\b")),
    ("network-other", re.compile(r"Connection refused|Connection reset|SSL|certificate|Failed to connect|Could not connect|socket hang up|ECONNREFUSED|ECONNRESET", re.I)),
    ("arg-usage", re.compile(r"unknown option|unrecognized option|invalid option|illegal option|usage: |requires an argument|unknown flag|flag provided but not defined|unknown field|invalid argument|Invalid value", re.I)),
]
BAZEL_RE = re.compile(r"Build did NOT complete|Analysis failed|no such (package|target)|ERROR: |Unrecognized option|Invocation ID|Loading failed|FAILED in|FATAL: |Output base")


def expected_kind(seg, cmd, exit_code, out):
    """Return a benign-nonzero label or None."""
    p, sub = seg["prog"], seg["sub"]
    if p == "git" and sub in ("rebase", "merge", "cherry-pick", "revert", "stash", "am", "pull", "checkout", "switch") and CONFLICT_RE.search(out):
        return "conflict"
    if exit_code is None or exit_code == 0:
        return None
    if p in ("rg", "grep", "egrep", "fgrep", "ag") and exit_code == 1:
        return "no-match"
    if p in ("diff", "cmp", "colordiff") and exit_code == 1:
        return "diff-found"
    if p in ("test", "[", "[[") and exit_code == 1:
        return "test-false"
    if p == "git":
        if sub == "diff" and re.search(r"--(quiet|exit-code)\b", cmd or "") and exit_code == 1:
            return "diff-found"
        if sub in ("show-ref", "merge-base", "check-ignore", "config") and exit_code == 1:
            return "probe"
        if sub == "rev-parse" and "--verify" in (cmd or "") and "--quiet" in (cmd or "") and exit_code == 1:
            return "probe"
        if sub == "ls-remote" and "--exit-code" in (cmd or "") and exit_code == 2:
            return "probe"
        if sub == "grep" and exit_code == 1:
            return "no-match"
    if p in ("command", "which", "type", "pgrep", "pkill", "kill", "printenv", "ps") and exit_code == 1:
        return "probe"
    if p == "git" and sub == "diff" and "--no-index" in (cmd or "") and exit_code == 1:
        return "diff-found"
    if "2>/dev/null" in (cmd or "") and not out.strip() and p in ("ls", "test", "[", "cat", "stat", "grep", "rg", "git", "jq"):
        return "silent-probe"
    if "agent wait" in (cmd or "") and "timed out waiting for agent status" in out:
        return "poll-timeout"
    if p == "gh" and sub == "pr" and re.search(r"\bchecks\b", cmd or "") and exit_code in (1, 8):
        return "status-report"
    is_test = (p in ("pytest", "jest", "vitest", "tox")
               or (p.startswith("python") and seg["sub"] == "-m pytest")
               or (p in ("bazel", "bazelisk", "cargo", "go") and sub == "test")
               or (p in ("npm", "pnpm", "yarn") and sub.startswith(("test", "run test"))))
    if is_test and TEST_FAIL_RE.search(out) and not BUILD_ERR_RE.search(out):
        return "test-failures"
    return None


def classify(seg, cmd, exit_code, out, escalated):
    """Return (status, cluster, expected_label)."""
    if exit_code == 0:
        return "ok", None, None
    if exit_code is None:
        return "unattr", None, None
    head = out
    if USER_RE.search(head):
        return "user-denied", "user-denied", None
    if SANDBOX_RE.search(head):
        return "sandbox", "sandbox-block", None
    if NETWORK_RE.search(head):
        return "network", "network-blocked", None
    exp = expected_kind(seg, cmd, exit_code, out) if seg else None
    if exp:
        return "expected", exp, exp
    prog = seg["prog"] if seg else ""
    if prog in ("bazel", "bazelisk") and BAZEL_RE.search(head):
        if re.search(r"Output base directory", head):
            return "real", "bazel-output-base", None
        if re.search(r"Build did NOT complete|Analysis failed|ERROR: [^\n]*(BUILD|\.bzl|/BUILD)", head):
            return "real", "bazel-build-error", None
        return "real", "bazel-other", None
    for name, rx in CLUSTERS:
        m = rx.search(head)
        if m:
            if name == "python-exception":
                names = re.findall(r"\b([A-Za-z]+(?:Error|Exception))\b", head)
                return "real", ("python:" + names[-1]) if names else "python-traceback", None
            return "real", name, None
    if exit_code == 124:
        return "real", "timeout", None
    if not out.strip():
        return "real", "silent-nonzero", None
    return "real", "other", None


def redact(s):
    s = re.sub(r"(?i)(password|passwd|token|secret|api[_-]?key|authorization|bearer)(\s*[:=]\s*|\s+)\S+", r"\1=<REDACTED>", s)
    s = re.sub(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|xox[baprs]-[A-Za-z0-9\-]+|AKIA[0-9A-Z]{16})\b", "<REDACTED>", s)
    s = re.sub(r"([?&](token|key|sig|access_token|api_key)=)[^&\s]+", r"\1<REDACTED>", s)
    s = re.sub(r"\b[A-Fa-f0-9]{32,}\b", "<HEX-REDACTED>", s)
    s = re.sub(r"\b[A-Za-z0-9_\-]{40,}\b", "<LONG-REDACTED>", s)
    return s


# ------------------------------------------------------------ result parsing
def items_of(output):
    """Normalize a function/custom output into a list of (type, text)."""
    if output is None:
        return []
    if isinstance(output, list):
        res = []
        for x in output:
            if isinstance(x, dict):
                res.append((x.get("type", ""), x.get("text", "")))
        return res
    return [("text", str(output))]


def header_of(text):
    for h in ("Script completed", "Script failed", "Script running", "aborted by user"):
        if text.startswith(h):
            return h
    return None


def body_after_output(text):
    i = text.find("Output:\n")
    return text[i + len("Output:\n"):] if i >= 0 else text


def parse_result(text):
    """Return (exit_code or None, method, body) for one inner or top-level result."""
    m = re.search(r"Process exited with code (\d+)", text)
    if m:
        return int(m.group(1)), "header", body_after_output(text)
    m = re.match(r"\s*Exit code: (\d+)", text)
    if m:
        return int(m.group(1)), "header", body_after_output(text)
    idx = text.find("{")
    if idx >= 0 and "exit_code" in text[idx:idx + 2000]:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[idx:])
            code = obj.get("exit_code")
            if code is None and isinstance(obj.get("metadata"), dict):
                code = obj["metadata"].get("exit_code")
            if code is not None:
                return int(code), "json", str(obj.get("output", text))
        except ValueError:
            pass
    if text.startswith("Success. Updated") or text.startswith('{"output":"Success. Updated'):
        return 0, "text", text
    if "apply_patch verification failed" in text[:300] or text.startswith("Failed to find expected"):
        return 1, "text", text
    if "stdin is closed" in text[:300]:
        return 1, "text", text
    return None, None, text


# ----------------------------------------------------------- record builder
def month_of(ts):
    return ts[:7]


def unit(**kw):
    base = {
        "kind": "shell", "tool": "", "src": "", "file": "", "ts": "", "month": "",
        "call_id": "", "cell": "", "attr": "", "attr_detail": "", "exit": None, "method": "",
        "status": "", "cluster": "", "expected": "", "escalated": False, "keys": [],
        "key": "", "cmd": "", "body": "", "rg_cfg_warn": False, "bwrap": False,
        "unattr_reason": "", "text_fail": False,
    }
    base.update(kw)
    return base


def shell_keys(segs):
    if not segs:
        return ["UNRESOLVED-CMD"]
    keys = []
    for s in segs:
        k = seg_key(s)
        if k not in keys:
            keys.append(k)
    return keys


def finish_shell(u, cmd, segs, out_text, exit_code, method):
    """Fill status, cluster, key for a shell unit with a known or unknown exit code."""
    u["exit"] = exit_code
    u["method"] = method or ""
    u["cmd"] = (cmd or "")[:3000]
    u["keys"] = shell_keys(segs)
    seg, how = attribute_segment(segs, out_text) if segs else (None, "unresolved")
    u["key"] = seg_key(seg) if seg else "UNRESOLVED-CMD"
    u["attr_detail"] = how
    if exit_code is None:
        u["status"] = "unattr"
        u["cluster"] = ""
    else:
        status, cluster, exp = classify(seg, cmd or "", exit_code, out_text, u["escalated"])
        u["status"], u["cluster"], u["expected"] = status, cluster or "", exp or ""
    u["body"] = redact(out_text[:700])
    u["rg_cfg_warn"] = "RIPGREP_CONFIG_PATH" in out_text
    u["bwrap"] = "bwrap" in out_text
    u["text_fail"] = bool(exit_code is None and (CONFLICT_RE.search(out_text) or SANDBOX_RE.search(out_text)
                                                   or re.search(r"\bfatal: |command not found|No such file or directory|Traceback \(most recent", out_text)))


def other_tool_status(name, out_text):
    """Error detection for non-shell tools, using their own output text."""
    head = out_text[:1500]
    pats = [
        (r"^failed to parse function arguments", "invalid-args"),
        (r"^write_stdin failed", "stdin-closed"),
        (r"^collab (spawn |tool )?failed|agent thread limit reached", "agent-limit"),
        (r"timeout_ms must be|agent_name must|absolute agent paths|live agent path|fork_context is not supported", "invalid-args"),
        (r"request_user_input is unavailable", "unavailable-mode"),
        (r"^Error code: |tool call error|Error calling MCP tool|\"isError\": ?true|invalid_auth", "mcp-error"),
    ]
    is_mcp = name.startswith("mcp__") or name.startswith("_")
    if is_mcp:
        short = out_text[:400]
        if re.search(r"requires approval, but approval policy is never", short):
            return "blocked", "mcp-approval-policy"
        if re.search(r"host blocks the sandbox", short):
            return "blocked", "mcp-host-sandbox-block"
        if re.search(r"invalid_auth|\bUnauthorized\b|\bForbidden\b|HTTP[ /]40[13]\b|\b40[13] (Unauthorized|Forbidden)", short):
            return "real", "mcp-auth"
        if re.search(r"Transport send error", short):
            return "real", "mcp-transport"
    for rx, label in pats:
        if not is_mcp and label == "mcp-error":
            continue
        if re.search(rx, head, re.M):
            return "real", label
    if name == "wait" and not head.startswith("Script") and "aborted by user" not in head:
        return "real", "wait-error"
    return "ok", ""


def mcp_server(name):
    """Server for mcp__<server>__<tool> names. Top-level '_xxx' names carry no server, so infer it (labelled)."""
    m = re.match(r"mcp__([^_]+(?:_[^_]+)*?)__", name)
    if m:
        return m.group(1)
    if name.startswith("_"):
        n = name.lower()
        if "slack" in n:
            return "codex_apps:slack(inferred)"
        if any(k in n for k in ("jira", "atlassian", "transition", "addcomment", "accessible")):
            return "codex_apps:atlassian(inferred)"
        if "notion" in n:
            return "codex_apps:notion(inferred)"
        return "codex_apps:github(inferred)"
    return ""


def build(files):
    units = []
    stats = collections.Counter()
    for path in files:
        recs = []
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    stats["bad_json_lines"] += 1
        calls, outs = [], {}
        patch_ev = {}
        for r in recs:
            pl = r.get("payload") or {}
            if r.get("type") == "event_msg" and pl.get("type") == "patch_apply_end":
                patch_ev[pl.get("call_id")] = (pl.get("success"), pl.get("stderr") or "")
        for idx, r in enumerate(recs):
            pl = r.get("payload") or {}
            if r.get("type") != "response_item":
                continue
            t = pl.get("type")
            if t in ("function_call", "custom_tool_call"):
                calls.append({"idx": idx, "ts": r.get("timestamp", ""), "kind": t,
                              "name": pl.get("name") or "", "cid": pl.get("call_id"),
                              "arg": pl.get("arguments") if t == "function_call" else pl.get("input")})
            elif t in ("function_call_output", "custom_tool_call_output"):
                outs[pl.get("call_id")] = {"idx": idx, "out": pl.get("output")}

        def arg_obj(c):
            if c["kind"] != "function_call":
                return {}
            try:
                return json.loads(c["arg"] or "{}")
            except ValueError:
                return {}

        # ---- chains: direct exec_command sessions and code-mode cells
        session_chain = {}  # exec call cid -> list of output texts (write_stdin results)
        cell_chain = {}     # exec(JS) call cid -> list of wait output texts
        for c in calls:
            if c["cid"] not in outs:
                continue
            txt = " ".join(x[1] for x in items_of(outs[c["cid"]]["out"]))
            if c["name"] == "exec_command" and c["kind"] == "function_call":
                m = re.search(r"Process running with session ID (\d+)", txt)
                if m:
                    sid = m.group(1)
                    follow = []
                    for d in calls:
                        if d["idx"] <= c["idx"] or d["name"] != "write_stdin" or d["cid"] not in outs:
                            continue
                        if str(arg_obj(d).get("session_id")) != sid:
                            continue
                        dtxt = " ".join(x[1] for x in items_of(outs[d["cid"]]["out"]))
                        follow.append(dtxt)
                        if re.search(r"Process exited with code", dtxt):
                            break
                    session_chain[c["cid"]] = follow
            if c["name"] == "exec" and c["kind"] == "custom_tool_call":
                m = re.search(r"Script running with cell ID (\d+)", txt)
                if m:
                    cid = m.group(1)
                    follow = []
                    for d in calls:
                        if d["idx"] <= c["idx"] or d["name"] != "wait" or d["cid"] not in outs:
                            continue
                        if str(arg_obj(d).get("cell_id")) != cid:
                            continue
                        dtxt = " ".join(x[1] for x in items_of(outs[d["cid"]]["out"]))
                        follow.append((d["cid"], dtxt))
                        if header_of(dtxt) != "Script running":
                            break
                    cell_chain[c["cid"]] = follow

        carrier_ids = set()
        for c in calls:
            if c["cid"] in cell_chain:
                carrier_ids.update(x[0] for x in cell_chain[c["cid"]])

        # ---- main pass
        for c in calls:
            if not (WIN_LO <= c["ts"][:10] <= WIN_HI):
                stats["out_of_window_calls"] += 1
                continue
            stats["in_window_calls"] += 1
            cid = c["cid"]
            o = outs.get(cid)
            name = c["name"]
            ts = c["ts"]
            fname = os.path.basename(path)
            base = dict(file=fname, ts=ts, month=month_of(ts), call_id=cid or "")
            if o is None:
                stats["no_output_" + name] += 1
                if name == "exec":
                    units.append(unit(kind="cell", tool="exec(JS)", src="code", status="no-output", **base))
                elif name == "exec_command":
                    a = arg_obj(c)
                    segs = normalize_cmd(a.get("cmd"))
                    units.append(unit(kind="shell", tool="exec_command", src="direct", escalated=a.get("sandbox_permissions") == "require_escalated",
                                      status="unattr", unattr_reason="no-output", cmd=str(a.get("cmd", ""))[:3000],
                                      keys=shell_keys(segs), key=(seg_key(segs[-1]) if segs else "UNRESOLVED-CMD"), **base))
                else:
                    units.append(unit(kind="tool", tool=name, src="top", status="unattr", unattr_reason="no-output", **base))
                continue

            its = items_of(o["out"])
            txt_all = " ".join(x[1] for x in its)

            if name == "exec_command" and c["kind"] == "function_call":
                a = arg_obj(c)
                cmd = a.get("cmd")
                segs = normalize_cmd(cmd) if isinstance(cmd, str) else None
                esc = a.get("sandbox_permissions") == "require_escalated"
                exit_code, method, body = parse_result(txt_all)
                if exit_code is None and cid in session_chain:
                    for ft in session_chain[cid]:
                        ec, _, _ = parse_result(ft)
                        if ec is not None and re.search(r"Process exited with code", ft):
                            exit_code, method, body = ec, "chain", body_after_output(ft)
                            break
                if exit_code is None and "aborted by user" in txt_all:
                    u = unit(kind="shell", tool="exec_command", src="direct", escalated=esc, status="aborted", cmd=str(cmd)[:3000], **base)
                    u["keys"] = shell_keys(segs)
                    u["key"] = seg_key(segs[-1]) if segs else "UNRESOLVED-CMD"
                    u["body"] = redact(txt_all[:700])
                    units.append(u)
                    continue
                u = unit(kind="shell", tool="exec_command", src="direct", escalated=esc, **base)
                if exit_code is None and cid in session_chain:
                    u["unattr_reason"] = "session-not-finished"
                finish_shell(u, cmd if isinstance(cmd, str) else None, segs, body, exit_code, method)
                if exit_code is None and not u["unattr_reason"]:
                    u["unattr_reason"] = "exit-not-printed"
                if cmd is None:
                    u["unattr_reason"] = u["unattr_reason"] or "unparsed-args"
                units.append(u)
                continue

            if name == "exec" and c["kind"] == "custom_tool_call":
                js = c["arg"] or ""
                inner = [(t, a) for (t, a, _) in parse_inner(js) if t not in NON_RESULT_TOOLS]
                has_loop = bool(LOOP_RE.search(js))
                # full text items for the cell (including wait chain)
                chain_texts = [txt_all]
                final_hdr = header_of(txt_all)
                chain_items = list(its)
                if cid in cell_chain:
                    for wid, wtxt in cell_chain[cid]:
                        wo = outs.get(wid)
                        if wo is None:
                            continue
                        wits = items_of(wo["out"])
                        chain_items.extend(wits)
                        final_hdr = header_of(" ".join(x[1] for x in wits)) or final_hdr
                body_items = [t for (ty, t) in chain_items
                              if ty in ("input_text", "text") and not header_of(t)]
                if final_hdr == "Script failed":
                    body_items_wrapper = body_items
                else:
                    body_items_wrapper = body_items
                # inner results: drop the wrapper's own error item so it is not read as a printed result
                result_items = [t for t in body_items if not t.startswith("Script error")]
                # cell-level status
                if final_hdr == "Script completed":
                    cstatus, ccluster = "ok", ""
                elif final_hdr == "Script failed":
                    err = " ".join(body_items_wrapper)
                    cstatus = "js-failed"
                    ccluster = "js-wrapper:" + next((n for n, rx in [
                        ("apply_patch-context", re.compile(r"apply_patch verification failed|Failed to find expected")),
                        ("sandbox-block", SANDBOX_RE),
                        ("js-syntax-or-exception", re.compile(r"SyntaxError|ReferenceError|is not defined|Unexpected token|is not a function|Cannot read propert|TypeError")),
                        ("tool-call-error", re.compile(r"write_stdin failed|tool call|Error code|not found|failed")),
                    ] if rx.search(err)), "other")
                elif final_hdr == "aborted by user":
                    cstatus, ccluster = "aborted", ""
                elif final_hdr is None and txt_all.strip() == "":
                    cstatus, ccluster = "no-output", ""
                else:
                    cstatus, ccluster = "unresolved", ""
                units.append(unit(kind="cell", tool="exec(JS)", src="code", status=cstatus, cluster=ccluster,
                                  cell=str(cid), body=redact(" | ".join(body_items_wrapper)[:600]), **base))

                # attribution of inner calls
                S = len(inner)
                body_items = result_items
                K = len(body_items)
                if S == 0:
                    stats["cells_without_inner_calls"] += 1
                    continue
                pairs = []  # list of (tool, args, result_text or None, reason)
                if K == 0:
                    why = "no-output-printed" if final_hdr == "Script completed" else "cell-" + cstatus
                    for (t, a) in inner:
                        pairs.append((t, a, None, why))
                elif S == 1 and has_loop:
                    t, a = inner[0]
                    for it in body_items:
                        pairs.append((t, a, it, "loop-template"))
                elif S == 1 and K == 1:
                    t, a = inner[0]
                    pairs.append((t, a, body_items[0], "single"))
                elif S == K:
                    for (t, a), it in zip(inner, body_items):
                        pairs.append((t, a, it, "order" if not has_loop else "order-loop"))
                elif has_loop:
                    for (t, a) in inner:
                        pairs.append((t, a, None, "loop-multi-call"))
                else:
                    for (t, a) in inner:
                        pairs.append((t, a, None, "count-mismatch(S=%d,K=%d)" % (S, K)))

                for t, a, rtext, reason in pairs:
                    ib = dict(file=fname, ts=ts, month=month_of(ts), call_id=cid or "", cell=str(cid))
                    if t == "exec_command":
                        cmd = a.get("cmd") if isinstance(a, dict) else None
                        cmd_s = cmd if isinstance(cmd, str) else None
                        if isinstance(cmd, tuple) and cmd[0] == "TEMPLATE":
                            cmd_s = cmd[1]  # template literal: keep placeholders, program is still readable
                        segs = normalize_cmd(cmd_s) if cmd_s is not None else None
                        esc = isinstance(a, dict) and a.get("sandbox_permissions") == "require_escalated"
                        if a is None and rtext is None:
                            units.append(unit(kind="shell", tool="exec_command", src="code", status="unattr",
                                              unattr_reason="unparsed-args", keys=["UNRESOLVED-CMD"],
                                              key="UNRESOLVED-CMD", **ib))
                            continue
                        if rtext is None:
                            u = unit(kind="shell", tool="exec_command", src="code", escalated=esc, status="unattr",
                                     unattr_reason=reason, cmd=(cmd_s or "")[:3000], keys=shell_keys(segs),
                                     key=(seg_key(segs[-1]) if segs else "UNRESOLVED-CMD"), **ib)
                            units.append(u)
                            continue
                        ec, method, body = parse_result(rtext)
                        if ec is None:
                            reason2 = "still-running-in-cell" if "Process running with session ID" in rtext else "exit-not-printed"
                            u = unit(kind="shell", tool="exec_command", src="code", escalated=esc, status="unattr",
                                     unattr_reason=reason2, cmd=(cmd_s or "")[:3000], keys=shell_keys(segs),
                                     key=(seg_key(segs[-1]) if segs else "UNRESOLVED-CMD"), body=redact(rtext[:700]), **ib)
                            u["text_fail"] = bool(TEXT_FAIL_RE.search(rtext))
                            u["bwrap"] = "bwrap" in rtext
                            u["rg_cfg_warn"] = "RIPGREP_CONFIG_PATH" in rtext
                            units.append(u)
                            continue
                        u = unit(kind="shell", tool="exec_command", src="code", escalated=esc, **ib)
                        if cmd_s is None:
                            u["unattr_reason"] = "cmd-unresolved"
                            u["exit"] = ec
                            u["method"] = method
                            u["keys"] = ["UNRESOLVED-CMD"]
                            u["key"] = "UNRESOLVED-CMD"
                            u["body"] = redact(body[:700])
                            u["attr"] = reason
                            status, cluster, exp = classify(None, "", ec, body, esc)
                            u["status"], u["cluster"], u["expected"] = status, cluster or "", exp or ""
                            units.append(u)
                            continue
                        finish_shell(u, cmd_s, segs, body, ec, method)
                        u["attr"] = reason
                        units.append(u)
                    else:
                        # inner non-shell tool (apply_patch, write_stdin, MCP, ...)
                        u = unit(kind="tool", tool=t, src="code", **ib)
                        u["attr"] = reason
                        if rtext is None:
                            u["status"], u["unattr_reason"] = "unattr", reason
                            units.append(u)
                            continue
                        ec, method, body = parse_result(rtext)
                        if t == "apply_patch":
                            if ec is None and cstatus == "ok" and not re.search(r"verification failed|Failed to|Error", rtext):
                                u["status"], u["method"], u["exit"] = "ok", "cell-completed", 0
                                u["body"] = redact(rtext[:200])
                            elif ec is None:
                                u["status"], u["unattr_reason"] = "unattr", "no-signal"
                            else:
                                u["exit"], u["method"] = ec, method
                                u["status"] = "ok" if ec == 0 else "real"
                                u["cluster"] = "" if ec == 0 else ("apply-patch-context" if "verification failed" in rtext or "Failed to find" in rtext else "apply-patch-other")
                                u["body"] = redact(rtext[:500])
                        else:
                            st, label = other_tool_status(t, rtext)
                            u["status"], u["cluster"] = st, label
                            u["body"] = redact(rtext[:500])
                            u["method"] = "text"
                        if t.startswith("mcp__"):
                            u["cluster"] = u["cluster"] or ""
                            u["key"] = "mcp:" + (mcp_server(t) or "?")
                        units.append(u)
                continue

            # ---- top-level non-shell tools
            if name == "apply_patch" and c["kind"] == "custom_tool_call":
                ec, method, body = parse_result(txt_all)
                u = unit(kind="tool", tool="apply_patch", src="top", **base)
                if cid in patch_ev:
                    ok_flag, err = patch_ev[cid]
                    u["method"] = "event"
                    u["exit"] = 0 if ok_flag else 1
                    u["body"] = redact(err[:500])
                    if ok_flag:
                        u["status"] = "ok"
                    elif "rejected by user" in err:
                        u["status"], u["cluster"] = "user-denied", "user-denied"
                    else:
                        u["status"] = "real"
                        u["cluster"] = ("apply-patch-context" if "Failed to find expected" in err
                                        else "apply-patch-io" if re.search(r"Failed to (create|write)", err)
                                        else "apply-patch-other")
                elif ec is None:
                    u["status"], u["unattr_reason"] = "unattr", "no-signal"
                else:
                    u["exit"], u["method"] = ec, method
                    u["status"] = "ok" if ec == 0 else "real"
                    u["cluster"] = "" if ec == 0 else ("apply-patch-context" if "verification failed" in txt_all or "Failed to find" in txt_all else "apply-patch-other")
                    u["body"] = redact(txt_all[:500])
                units.append(u)
                continue
            if name == "exec_command" and c["kind"] == "function_call":
                continue  # handled above
            if name == "write_stdin" and c["kind"] == "function_call":
                st, label = other_tool_status("write_stdin", txt_all)
                units.append(unit(kind="tool", tool="write_stdin", src="top", status=st, cluster=label, body=redact(txt_all[:400]), **base))
                continue
            if name == "wait" and c["kind"] == "function_call":
                if c["cid"] in carrier_ids:
                    stats["wait_carrier_calls"] += 1
                st, label = other_tool_status("wait", txt_all)
                units.append(unit(kind="tool", tool="wait", src="top", status=st, cluster=label, body=redact(txt_all[:400]), **base))
                continue
            if name == "exec" and c["kind"] == "custom_tool_call":
                continue
            # any other tool (agents, sleep, MCP, plan, etc.)
            st, label = other_tool_status(name, txt_all)
            u = unit(kind="tool", tool=name, src="top", status=st, cluster=label, body=redact(txt_all[:400]), **base)
            if name.startswith("_") or name.startswith("mcp__"):
                u["key"] = "mcp:" + (mcp_server(name) or "?")
            units.append(u)
    return units, stats


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(ROOT, "**/*.jsonl"), recursive=True))
    units, stats = build(files)
    with open(OUT, "w") as f:
        for u in units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print("files", len(files), "units", len(units))
    print(dict(stats))
    with open(os.path.join(OUT_DIR, "stats.json"), "w") as f:
        json.dump({"files": len(files), "units": len(units), **dict(stats)}, f, indent=1)
    c = collections.Counter((u["kind"], u["src"], u["status"]) for u in units)
    for k, v in sorted(c.items()):
        print(k, v)


if __name__ == "__main__":
    main()
