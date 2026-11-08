/**
 * The model step: a chain of reviewers, cheapest first. The first decides plain cases;
 * the last takes what earlier ones are unsure about and anything that runs a script.
 * A reviewer that fails or times out denies.
 */
import { type Decision, type ReviewInput, REVIEW_SYSTEM, parseVerdict, reviewPrompt } from "./policy.ts";

type Reply = { content: { type: string; text?: string }[]; stopReason?: string; errorMessage?: string };

/** The slice of Pi's ModelRegistry this needs, so the eval can pass its own. */
export interface Registry {
  find(provider: string, id: string): unknown;
  streamSimple(model: never, context: unknown, options?: unknown): { result(): Promise<Reply> };
}

export interface ModelRef { provider: string; id: string; reasoning?: string }

/** "provider/model" or "provider/model:effort", e.g. "openai-codex/gpt-6.1-terra:minimal". */
export function parseRef(spec: string): ModelRef {
  const [path, reasoning] = spec.split(":");
  const slash = path.indexOf("/");
  return { provider: path.slice(0, slash), id: path.slice(slash + 1), reasoning };
}

/**
 * Haiku alone: in eval.ts it blocked every adversarial command, and adding Sonnet or the
 * GPT-6.1 models behind it blocked more harmless ones without blocking more harmful ones.
 * Override with PI_AUTO_MODE_MODELS="first,second".
 */
export const DEFAULT_CHAIN = (process.env.PI_AUTO_MODE_MODELS ?? "anthropic/claude-haiku-5-5")
  .split(",").map((s) => parseRef(s.trim()));

const TIMEOUT_MS = 20_000;
const LOGIN_ERROR = /oauth|invalid_grant|unauthori[sz]ed|\b40[13]\b|api key|credential|log ?in/i;

/** Provider errors can carry whole stack traces; the agent needs one line. */
function short(message: string): string {
  return message.split("\n")[0].replace(/; (details|stack)=.*/, "").slice(0, 200);
}

export async function askModel(registry: Registry, ref: ModelRef, input: ReviewInput): Promise<Decision> {
  const name = `${ref.id}${ref.reasoning ? `:${ref.reasoning}` : ""}`;
  const failed = (why: string): Decision => ({
    verdict: "deny",
    reason: `Command reviewer failed (${short(why)}), so the command was not run.`,
    by: name,
    unavailable: LOGIN_ERROR.test(why) ? "login" : "error",
  });
  const model = registry.find(ref.provider, ref.id);
  if (!model) return failed(`${ref.provider}/${ref.id} is not available`);
  try {
    const reply = await registry.streamSimple(model as never, {
      systemPrompt: REVIEW_SYSTEM,
      messages: [{ role: "user", content: reviewPrompt(input), timestamp: Date.now() }],
    }, { maxTokens: 2000, signal: AbortSignal.timeout(TIMEOUT_MS), ...(ref.reasoning ? { reasoning: ref.reasoning } : {}) }).result();
    if (reply.stopReason === "error" || reply.stopReason === "aborted") return failed(reply.errorMessage ?? reply.stopReason);
    const text = reply.content.filter((c) => c.type === "text").map((c) => c.text ?? "").join("");
    return parseVerdict(text, name);
  } catch (e) {
    return failed((e as Error).message);
  }
}

export async function review(registry: Registry, input: ReviewInput, chain: ModelRef[] = DEFAULT_CHAIN): Promise<Decision> {
  // A script's effect is in its contents, so it goes straight to the strongest reviewer.
  const steps = input.scripts.length ? chain.slice(-1) : chain;
  let last: Decision | undefined;
  for (const ref of steps) {
    last = await askModel(registry, ref, input);
    // An unreachable reviewer hands over to the next one, like an unsure one.
    if (last.verdict !== "unsure" && !last.unavailable) return last;
  }
  if (last!.unavailable) return last!;
  return { ...last!, verdict: "deny", reason: `Not clearly safe: ${last!.reason} Find a narrower command that stays inside the worktree.` };
}
