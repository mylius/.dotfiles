/**
 * Auto mode for unattended Pi runs: every tool call passes a rule check, and anything
 * the rules don't settle goes to a Claude reviewer before it runs. A denied call returns
 * its reason to the agent, which adapts instead of stopping.
 *
 *   pi -e ~/.dotfiles/agents/pi/auto-mode/index.ts [--auto-mode-models provider/model,...]
 *
 * Decisions are appended to $XDG_STATE_HOME/pi-auto-mode.jsonl.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { type Call, type Decision, executedScripts, fastDecision } from "./policy.ts";
import { DEFAULT_CHAIN, type Registry, parseRef, review } from "./review.ts";

const STATE = process.env.XDG_STATE_HOME ?? join(homedir(), ".local", "state");
const LOG = join(STATE, "pi-auto-mode.jsonl");

function log(entry: Record<string, unknown>) {
  try {
    mkdirSync(STATE, { recursive: true });
    appendFileSync(LOG, `${JSON.stringify({ at: new Date().toISOString(), ...entry })}\n`);
  } catch {}
}

function text(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.filter((c) => c?.type === "text").map((c) => c.text).join("\n");
}

export default function autoMode(pi: ExtensionAPI) {
  pi.registerFlag("auto-mode-models", {
    description: "Command reviewers, cheapest first, as provider/model[:effort],...",
    type: "string",
  });
  const chain = () => {
    const flag = pi.getFlag("auto-mode-models");
    return typeof flag === "string" && flag ? flag.split(",").map((s) => parseRef(s.trim())) : DEFAULT_CHAIN;
  };

  pi.on("tool_call", async (event, ctx) => {
    const root = ctx.sessionManager.getCwd();
    const input = (event.input ?? {}) as Record<string, unknown>;
    const call: Call = {
      tool: event.toolName,
      command: typeof input.command === "string" ? input.command : undefined,
      path: typeof input.path === "string" ? input.path : undefined,
    };

    let decision: Decision | null = fastDecision(call, root);
    if (!decision) {
      const messages = ctx.sessionManager.getBranch()
        .filter((e: any) => e.type === "message")
        .map((e: any) => e.message);
      const brief = text(messages.find((m: any) => m.role === "user")?.content);
      const recent = messages.filter((m: any) => m.role === "assistant").slice(-2).map((m: any) => text(m.content)).filter(Boolean);
      const command = call.command ?? `${call.tool} ${JSON.stringify(input).slice(0, 2000)}`;
      const request = { root, brief, recent, command, scripts: call.command ? executedScripts(call.command, root) : [] };
      decision = await review(ctx.modelRegistry as unknown as Registry, request, chain());
      // In T3 a select becomes a question in this thread, which the user or the parent
      // session can answer. Pi re-reads auth.json on use, so a fresh login needs no restart.
      while (decision.unavailable && ctx.hasUI && ctx.mode !== "print") {
        const fix = decision.unavailable === "login"
          ? `Its login has expired. Run \`pi\`, then /login, choose ${decision.by.includes("gpt") ? "OpenAI Codex" : "Anthropic"}, and pick Retry.`
          : "Check that the provider is reachable, then pick Retry.";
        const choice = await ctx.ui.select(
          `Auto mode can't review this command: ${decision.reason}\n${fix}\n\nCommand: ${command.slice(0, 300)}`,
          ["Retry", "Block this command"],
        );
        if (choice !== "Retry") break;
        decision = await review(ctx.modelRegistry as unknown as Registry, request, chain());
      }
    }

    log({ session: ctx.sessionManager.getSessionId(), root, tool: call.tool, command: call.command, path: call.path, ...decision });
    if (decision.verdict !== "allow") return { block: true, reason: `Auto mode blocked this: ${decision.reason}` };
    return undefined;
  });
}
