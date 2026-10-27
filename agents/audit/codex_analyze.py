#!/usr/bin/env python3
"""Aggregate data/units.jsonl into report.md (read-only on sessions; writes only under the audit dir)."""
import collections
import glob
import json
import os
import re

BASE = os.path.join(os.environ["AUDIT_OUT"], "codex")
UNITS = os.path.join(BASE, "data", "units.jsonl")
REPORT = os.path.join(BASE, "report.md")
ROOT = os.path.join(os.environ.get("WORKSPACE_ROOT") or os.path.expanduser("~"), ".codex/sessions")
WIN_LO, WIN_HI = os.environ["AUDIT_START"], os.environ["AUDIT_END"]

ATTRIB = {"ok", "expected", "sandbox", "network", "user-denied", "blocked", "real"}
BLOCKED = {"sandbox", "network", "user-denied", "blocked"}
REDACT_RE = [
    (re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key|authorization|bearer)(\s*[:=]\s*|\s+)\S+"), r"\1=<REDACTED>"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|xox[baprs]-[A-Za-z0-9\-]+|AKIA[0-9A-Z]{16})\b"), "<REDACTED>"),
    (re.compile(r"([?&](token|key|sig|access_token|api_key)=)[^&\s]+"), r"\1<REDACTED>"),
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), "<HEX-REDACTED>"),
    (re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"), "<LONG-REDACTED>"),
]
SKIP_LINE = re.compile(r"^(Warning: truncated|Total output lines|Chunk ID|Wall time|Output:|Script (completed|running|failed)|rg: failed to read the file specified in RIPGREP|Updating |Finished updating|\s*$)")


def redact(s):
    for rx, rep in REDACT_RE:
        s = rx.sub(rep, s)
    return s


def group_of(u):
    if u["kind"] == "cell":
        return "JS wrapper (exec cells)"
    if u["kind"] == "shell":
        return "shell exec_command (%s)" % ("direct" if u["src"] == "direct" else "code-mode inner")
    t = u["tool"]
    if t == "apply_patch":
        return "apply_patch (%s)" % ("top-level" if u["src"] == "top" else "code-mode inner")
    if t == "write_stdin":
        return "write_stdin (%s)" % ("top-level" if u["src"] == "top" else "code-mode inner")
    if t == "wait":
        return "wait (top-level, cell wait)"
    if u.get("key", "").startswith("mcp:"):
        return "MCP: " + u["key"][4:]
    if t.startswith("mcp__"):
        return "MCP: " + t.split("__")[1]
    if t in ("spawn_agent", "wait_agent", "send_message", "followup_task", "list_agents", "close_agent",
             "interrupt_agent", "send_agent_message", "list_stack_agents", "stack_status",
             "request_user_input", "request_user_input_async"):
        return "agent / orchestration (top-level)"
    return "other tool: " + t


def is_attrib(u):
    if u["kind"] == "cell":
        return u["status"] in ("ok", "js-failed")
    return u["status"] in ATTRIB


def pct(a, b):
    return "-" if not b else "%.1f%%" % (100.0 * a / b)


def first_line(body):
    for ln in (body or "").splitlines():
        if SKIP_LINE.match(ln):
            continue
        return ln.strip()[:160]
    return "(empty output)"


def patch_event_stats():
    """Counts of patch_apply_end events in the window (one per apply_patch execution)."""
    ev = collections.Counter()
    evfail = collections.Counter()
    for p in sorted(glob.glob(os.path.join(ROOT, "**/*.jsonl"), recursive=True)):
        for line in open(p, errors="replace"):
            if "patch_apply_end" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            pl = r.get("payload") or {}
            if r.get("type") != "event_msg" or pl.get("type") != "patch_apply_end":
                continue
            ts = r.get("timestamp", "")
            if not (WIN_LO <= ts[:10] <= WIN_HI):
                continue
            ev["events"] += 1
            if pl.get("success") is True:
                ev["success"] += 1
            else:
                ev["failed"] += 1
                err = pl.get("stderr") or ""
                lab = ("user rejected" if "rejected by user" in err else
                       "context mismatch" if "Failed to find expected" in err else
                       "parent dir / write error" if re.search(r"Failed to (create|write)", err) else "other")
                evfail[lab] += 1
    return ev, evfail


def raw_monthly_counts():
    """Raw tool-output counts per month for bwrap errors and the ripgrep config warning."""
    bw = collections.Counter()
    rg = collections.Counter()
    for p in sorted(glob.glob(os.path.join(ROOT, "**/*.jsonl"), recursive=True)):
        for line in open(p, errors="replace"):
            if "RIPGREP_CONFIG_PATH" not in line and "bwrap:" not in line and "fs sandbox helper" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ts = r.get("timestamp", "")
            if not (WIN_LO <= ts[:10] <= WIN_HI):
                continue
            pl = r.get("payload") or {}
            if r.get("type") != "response_item" or pl.get("type") not in ("function_call_output", "custom_tool_call_output"):
                continue
            o = pl.get("output")
            t = o if isinstance(o, str) else " ".join(x.get("text", "") for x in (o or []) if isinstance(x, dict))
            if "RIPGREP_CONFIG_PATH" in t:
                rg[ts[:7]] += 1
            if "bwrap:" in t or "fs sandbox helper" in t:
                bw[ts[:7]] += 1
    return bw, rg


def main():
    U = [json.loads(l) for l in open(UNITS)]
    U = [u for u in U if WIN_LO <= u["ts"][:10] <= WIN_HI]
    months = sorted({u["month"] for u in U if u["month"]})
    ev_total, ev_fail = patch_event_stats()
    out = []
    w = out.append
    stats = json.load(open(os.path.join(BASE, "data", "stats.json")))
    w("## 0. Scope, method, and limits\n")
    w("- Source: %d rollout files under $WORKSPACE_ROOT/.codex/sessions (main and sub-agent threads). Window: call timestamp UTC date %s to %s. "
      "In-window tool calls: %d; out of window: %d. Malformed JSON lines skipped: %d. Duplicate call IDs across files: none found. "
      "The session directory was still being written during this run, so out-of-window counts can grow; in-window results do not change." % (
          stats["files"], WIN_LO, WIN_HI, stats["in_window_calls"], stats["out_of_window_calls"], stats["bad_json_lines"]))
    w("- Units: one row per shell command (direct `exec_command` or code-mode inner `tools.exec_command`), per non-shell tool call, and per code-mode cell (the `exec` JS wrapper). "
      "A cell that yields (`Script running with cell ID N`) is joined to its `wait` calls with the same cell_id. A direct `exec_command` that yields a session is joined to `write_stdin` calls with the same session_id. "
      "`wait` and `write_stdin` carrier calls are counted as tool calls, but their shell or cell outcome is charged to the originating call only.")
    w("- Code-mode inner calls: the JS is parsed for `tools.X({...})` argument literals. A printed result is matched to an inner call when the number of printed results equals the number of inner calls (order mapping, checked on sampled cells), "
      "or when one inner call sits in a loop (each printed result is one execution), or when there is one inner call and one printed result. Otherwise the call is unattributable.")
    w("- Exit status comes from `Process exited with code N` (direct and chained sessions), from `exit_code` in a JSON result when the JS prints the result object, or from the `Exit code: N` header. "
      "apply_patch outcomes come from `patch_apply_end.success` for top-level calls, from `Success. Updated` or failure text for printed inner results, and from cell completion for inner calls that print `{}` in a completed cell. "
      "That last rule is an inference, not exact: a script that catches a failed patch can still complete.")
    w("- **Main limit:** when JS prints only `r.output`, the exit code never appears in the transcript. Those calls are unattributable (%d code-mode shell calls). Code-mode shell rates use only the subset whose exit code was printed. That subset is not a random sample: it is weighted to scripts that print JSON results." % (
        sum(1 for u in U if u["kind"] == "shell" and u["src"] == "code" and u["status"] == "unattr")))
    w("- Shell normalization: strip `cd X &&`, env assignments, `env -u`, `timeout N`, `sudo`, `nohup`, and `bash/zsh -lc` wrappers; split on `&&`, `||`, `;`, `|`, and newlines (not inside heredocs). Program+subcommand rules cover git, gh, bazel, kubectl, cargo, npm/pnpm/yarn, python -m, make, and similar.")
    w("- Failing segment: the segment named by a `command not found` message, else the segment whose name prefixes an error line (`gh: ...`), else the first segment whose name appears in the output, else the last segment. Method counts are in section 5.")
    w("- Expected and blocked classes are listed in section 3. Blocked (sandbox, network, user-denied, MCP approval policy, host sandbox block) is kept out of real failures.")
    w("- Real causes use regex clusters on the full output, first match wins. `other` and `silent-nonzero` are residual buckets.")
    w("- Rates are per attributable call, not per tool call. Totals in section 1 add across layers (cells, inner calls, top-level calls) and must not be read as one rate.")
    w("- Output text is redacted (tokens, long hex and base64 strings) before it is written to this report. Timestamps are UTC. Partial months at either end of the window have fewer calls. Raw bwrap and RIPGREP counts are text matches in tool output and can include ordinary output that quotes these strings.\n")

    # ------------------------------------------------ 1. per tool group
    groups = collections.defaultdict(list)
    for u in U:
        groups[group_of(u)].append(u)
    w("## 1. Failure rate per tool\n")
    w("Calls: one row per tool call (one per cell for the JS wrapper; one per printed result for code-mode loops). "
      "Attributable: calls whose own outcome is known from an exit code, or from explicit success/failure text for apply_patch and MCP. "
      "Real: unexpected failure. Blocked: sandbox, network, or user-denied. Expected: benign non-zero exits (section 3). "
      "Error rate incl. blocked = (real + blocked) / attributable.\n")
    w("| Tool group | Calls | Attributable | OK | Expected non-zero | Blocked | Real failures | Unattributable | Real rate | Error rate incl. blocked |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    tot = collections.Counter()
    aborted_notes = []
    for g in sorted(groups, key=lambda g: (-len(groups[g]), g)):
        L = groups[g]
        st = collections.Counter(u["status"] for u in L)
        if any(u["kind"] == "cell" for u in L):
            ok = st["ok"]; real = st["js-failed"]; attrib = ok + real
            exp = 0; blk = 0; unattr = st["unresolved"] + st["no-output"]
        else:
            ok = st["ok"]; exp = st["expected"]; blk = sum(st[x] for x in BLOCKED)
            real = st["real"]; attrib = ok + exp + blk + real; unattr = st["unattr"]
        if st["aborted"]:
            aborted_notes.append("%s: %d" % (g, st["aborted"]))
        w("| %s | %d | %d | %d | %d | %d | %d | %d | %s | %s |" % (
            g, len(L), attrib, ok, exp, blk, real, unattr, pct(real, attrib), pct(real + blk, attrib)))
        for k, v in zip(["calls", "attrib", "ok", "exp", "blk", "real", "unattr"], [len(L), attrib, ok, exp, blk, real, unattr]):
            tot[k] += v
    w("| **Total** | %d | %d | %d | %d | %d | %d | %d | %s | %s |" % (
        tot["calls"], tot["attrib"], tot["ok"], tot["exp"], tot["blk"], tot["real"], tot["unattr"],
        pct(tot["real"], tot["attrib"]), pct(tot["real"] + tot["blk"], tot["attrib"])))
    w("")
    w("User interrupts ('aborted by user') are excluded from every column: " + "; ".join(aborted_notes) + ".\n")

    # ------------------------------------------------ 2. shell by source
    shell = [u for u in U if u["kind"] == "shell"]
    w("## 2. Shell commands: exit-status classes by source\n")
    w("| Source | Shell calls | Exit known | Unattributable | Exit 0 | Expected non-zero | Blocked | Real failure | Real rate (of known) |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for src in ("direct", "code"):
        L = [u for u in shell if u["src"] == src]
        st = collections.Counter(u["status"] for u in L)
        known = st["ok"] + st["expected"] + st["sandbox"] + st["network"] + st["user-denied"] + st["real"]
        blk = st["sandbox"] + st["network"] + st["user-denied"]
        w("| %s | %d | %d | %d | %d | %d | %d | %d | %s |" % (
            "direct exec_command" if src == "direct" else "code-mode inner exec_command", len(L), known, st["unattr"],
            st["ok"], st["expected"], blk, st["real"], pct(st["real"], known)))
    w("")
    code_unattr = collections.Counter(u["unattr_reason"] for u in shell if u["src"] == "code" and u["status"] == "unattr")
    text_fail = sum(1 for u in shell if u["status"] == "unattr" and u.get("text_fail"))
    w("Unattributable code-mode shell calls, by reason: " + "; ".join("%s %d" % (k, v) for k, v in code_unattr.most_common()) + ".\n")
    w("Of all unattributable shell calls, %d contain explicit failure text (fatal:, command not found, No such file, Traceback, Read-only file system, bwrap, ERROR:, Permission denied, error:). "
      "This is a text heuristic and a lower bound on failures, not an exit code.\n" % text_fail)

    # ------------------------------------------------ 3. expected
    w("## 3. Expected non-zero exits and blocked classes (not counted as mistakes)\n")
    w("| Label | Count | Meaning |")
    w("|---|---:|---|")
    meaning = {
        "no-match": "rg/grep exit 1, no match",
        "diff-found": "diff/cmp exit 1, or git diff --quiet / --no-index exit 1 (differences exist)",
        "test-failures": "test runner exit non-zero with a failing-test report and no build error",
        "status-report": "gh pr checks exit 1 or 8 (pending or failing checks reported)",
        "probe": "command -v, which, type, pgrep, pkill, kill, printenv, ps, show-ref, merge-base --is-ancestor, config --get, rev-parse --verify --quiet",
        "silent-probe": "non-zero exit with empty output and stderr sent to /dev/null (ls, test, cat, stat, grep, rg, git, jq)",
        "conflict": "git rebase/merge/cherry-pick/revert/stash/am/pull/checkout/switch stopped on a conflict",
        "poll-timeout": "herdr agent wait gave up waiting for a status change",
        "test-false": "test or [ returned false",
    }
    exp = collections.Counter(u["expected"] for u in U if u["status"] == "expected")
    for k, v in exp.most_common():
        w("| %s | %d | %s |" % (k, v, meaning.get(k, "")))
    w("")
    sb_all = [u for u in shell if u["status"] == "sandbox"]
    nw_all = [u for u in shell if u["status"] == "network"]
    w("Blocked classes, kept apart from real mistakes:\n")
    w("- Sandbox: %d shell calls (direct %d, code-mode %d). Examples: `Read-only file system` on worktree index.lock writes, and `bwrap: loopback: Failed RTM_NEWADDR`." % (
        len(sb_all), sum(1 for u in sb_all if u["src"] == "direct"), sum(1 for u in sb_all if u["src"] == "code")))
    w("- Network: %d shell calls (direct %d, code-mode %d), e.g. DNS failures and `error connecting to api.github.com`." % (
        len(nw_all), sum(1 for u in nw_all if u["src"] == "direct"), sum(1 for u in nw_all if u["src"] == "code")))
    w("- User denied: %d shell calls. apply_patch executions that failed with `patch rejected by user` (from patch_apply_end events): %d." % (
        sum(1 for u in shell if u["status"] == "user-denied"), ev_fail.get("user rejected", 0)))
    w("")

    # ------------------------------------------------ 4. real failure clusters
    real_units = [u for u in U if u["status"] in ("real", "js-failed")]
    cl = collections.defaultdict(list)
    for u in real_units:
        cl[u["cluster"] or "(none)"].append(u)
    w("## 4. Real failures by cause\n")
    w("Counts cover shell calls, non-shell tools, and JS-wrapper failures (cell rows). Examples: the command (redacted, truncated) and its first output line (redacted).\n")
    w("| Cause | Count | Shell direct | Shell code | Non-shell tools | Cell wrapper | Example 1 | Example 2 |")
    w("|---|---:|---:|---:|---:|---:|---|---|")
    for label, L in sorted(cl.items(), key=lambda kv: -len(kv[1])):
        d = sum(1 for u in L if u["kind"] == "shell" and u["src"] == "direct")
        c = sum(1 for u in L if u["kind"] == "shell" and u["src"] == "code")
        t = sum(1 for u in L if u["kind"] == "tool")
        k = sum(1 for u in L if u["kind"] == "cell")
        ex = []
        for u in L[:2]:
            cmd = redact((u.get("cmd") or u.get("tool") or "")[:60]).replace("|", "\\|").replace("\n", " ")
            ex.append("`%s` -> %s" % (cmd, redact(first_line(u["body"])).replace("|", "\\|")))
        while len(ex) < 2:
            ex.append("")
        w("| %s | %d | %d | %d | %d | %d | %s | %s |" % (label, len(L), d, c, t, k, ex[0], ex[1]))
    w("")

    # ------------------------------------------------ 5. top 20 shell keys
    total = collections.Counter(); attrib_k = collections.Counter(); real_k = collections.Counter()
    causes_k = collections.defaultdict(collections.Counter)
    for u in shell:
        for k in u["keys"]:
            total[k] += 1
            if u["status"] in ATTRIB:
                attrib_k[k] += 1
        if u["status"] == "real":
            real_k[u["key"]] += 1
            causes_k[u["key"]][u["cluster"]] += 1
    w("## 5. Top 20 shell program+subcommand by real failures\n")
    w("Total: calls containing that segment. Attributable: those calls with a known outcome. Real: failures attributed to the segment (method in the report notes). Dominant cause: most common cluster among those failures.\n")
    w("| # | Program + subcommand | Total calls | Attributable | Real failures | Real rate | Dominant cause (count) |")
    w("|---:|---|---:|---:|---:|---:|---|")
    for i, (k, n) in enumerate(real_k.most_common(20), 1):
        dom = causes_k[k].most_common(1)[0]
        w("| %d | `%s` | %d | %d | %d | %s | %s (%d) |" % (i, k, total[k], attrib_k[k], n, pct(n, attrib_k[k]), dom[0], dom[1]))
    w("")
    attr_counts = collections.Counter(u["attr_detail"] for u in shell if u["status"] == "real" and u.get("attr_detail"))
    w("Failure-segment attribution method for real shell failures: " + ", ".join("%s %d" % kv for kv in attr_counts.most_common()) + ".\n")

    # ------------------------------------------------ 6. trend
    named = collections.Counter(u["cluster"] for u in real_units if u["cluster"] not in ("other", "silent-nonzero", "", "(none)"))
    top_causes = [c for c, _ in named.most_common(5)]
    bw, rg = raw_monthly_counts()
    w("## 6. Monthly trend\n")
    w("Months are UTC from the call timestamp. Partial months at either end of the window have fewer calls. Rows give failure counts. The first row gives attributable calls for scale.\n")
    attrib_by_m = collections.Counter(u["month"] for u in U if is_attrib(u))
    real_by_m = collections.defaultdict(collections.Counter)
    for u in real_units:
        real_by_m[u["cluster"]][u["month"]] += 1
    w("| Cause | " + " | ".join(months) + " |")
    w("|---|" + "---:|" * len(months))
    w("| (attributable calls) | " + " | ".join(str(attrib_by_m[m]) for m in months) + " |")
    for c in top_causes:
        w("| %s | " % c + " | ".join(str(real_by_m[c][m]) for m in months) + " |")
    sb = collections.Counter(u["month"] for u in U if u["status"] == "sandbox" and u.get("bwrap"))
    sro = collections.Counter(u["month"] for u in U if u["status"] == "sandbox" and "Read-only file system" in (u.get("body") or ""))
    sbo = collections.Counter(u["month"] for u in U if u["status"] == "sandbox")
    w("| sandbox blocks: bwrap (unit level, first 700 chars) | " + " | ".join(str(sb[m]) for m in months) + " |")
    w("| sandbox blocks: read-only file system (unit level) | " + " | ".join(str(sro[m]) for m in months) + " |")
    w("| sandbox blocks: all (unit level) | " + " | ".join(str(sbo[m]) for m in months) + " |")
    w("| bwrap error text in tool outputs (raw text match) | " + " | ".join(str(bw[m]) for m in months) + " |")
    w("| RIPGREP_CONFIG_PATH warning in tool outputs (raw text match) | " + " | ".join(str(rg[m]) for m in months) + " |")
    w("")
    w("Top causes used for the trend (excluding `other` and `silent-nonzero`): " + ", ".join("`%s`" % c for c in top_causes) + ".\n")

    # ------------------------------------------------ 7. apply_patch cross-check

    # ------------------------------------------------ 7. apply_patch cross-check
    w("## 7. apply_patch: event-level cross-check\n")
    w("patch_apply_end events in window: %d (success %d, failed %d). Failures by stderr: %s.\n" % (
        ev_total["events"], ev_total["success"], ev_total["failed"], ", ".join("%s %d" % kv for kv in ev_fail.most_common())))
    ap = [u for u in U if u["tool"] == "apply_patch"]
    w("apply_patch calls in the call-level view (top-level and code-mode inner): %d. Attributable: %d. Unattributable: %d. "
      "The call-level view uses events for top-level calls only; inner executions have no call ID in the output, so their outcome comes from printed text or the cell's completion (method `cell-completed`).\n" % (
          len(ap), sum(1 for u in ap if u["status"] in ATTRIB), sum(1 for u in ap if u["status"] == "unattr")))
    w("")

    # ------------------------------------------------ 8. unattributable
    w("## 8. Unattributable units\n")
    w("| Kind / source | Reason | Count |")
    w("|---|---|---:|")
    un = collections.Counter((u["kind"] + " / " + u["src"], u["unattr_reason"] or "-") for u in U if u["status"] in ("unattr", "unresolved", "no-output"))
    for (k, r), v in un.most_common(30):
        w("| %s | %s | %d |" % (k, r, v))
    w("")

    # ------------------------------------------------ 9. JS wrapper
    cells = [u for u in U if u["kind"] == "cell"]
    st = collections.Counter(u["status"] for u in cells)
    w("## 9. JS wrapper (exec cell) outcomes\n")
    w("Cells: %d. Completed: %d. Script failed (JS-level error): %d. Aborted by user: %d. Unresolved at end of data: %d. No output: %d.\n" % (
        len(cells), st["ok"], st["js-failed"], st["aborted"], st["unresolved"], st["no-output"]))
    cc = collections.Counter(u["cluster"] for u in cells if u["status"] == "js-failed")
    w("Script-failed causes: " + "; ".join("%s %d" % kv for kv in cc.most_common()) + ".\n")

    # ------------------------------------------------ 10. notes
    w("## 10. Notes on the data\n")
    rgw = [u for u in shell if u.get("rg_cfg_warn")]
    w("Shell units whose stored output (first 700 chars) contains the RIPGREP_CONFIG_PATH warning: %d, with outcomes %s. The warning is printed on stderr and does not change the exit code." % (
        len(rgw), ", ".join("%s %d" % kv for kv in collections.Counter(u["status"] for u in rgw).most_common())))

    open(REPORT, "w").write("# Codex tool and shell failure audit (%s to %s)\n\n" % (WIN_LO, WIN_HI) + "\n".join(out) + "\n")
    print("wrote", REPORT, "lines", len(out))


if __name__ == "__main__":
    main()
