# BytePlus ModelArk Coding Plan — operating card

## 0. Answering "can DeepSeek run on a subscription instead of API credits?"

Researched live 23/09/2026. **Yes — and this plan is that route. You already bought the answer.**

| Route | Subscription? | OAuth login? | DeepSeek included? |
|---|---|---|---|
| **DeepSeek first-party** (deepseek.com, platform.deepseek.com) | **No.** Pay-as-you-go only — *"The expense = number of tokens × price… deducted from your topped-up balance or granted balance"* | **No.** Bearer API key only | it is the source |
| **BytePlus ModelArk Coding Plan** ← you own this | **Yes**, flat monthly with a hard cap | No — a Coding-Plan-scoped API key | **Yes:** `deepseek-v4-pro`, `deepseek-v4-flash`, `deepseek-v3.2` |
| Alibaba Qwen / Bailian Coding Plan | Yes, ¥39–¥499/mo | No — API key | Yes, `deepseek-v4-pro-0813` |
| Atlas Cloud Coding Plan | Yes, $10–$500/mo | No — API key | Yes |
| Z.ai GLM · MiniMax · Kimi plans | Yes | No | **No DeepSeek** |
| OpenRouter | **No** — metered | No | Yes, metered only |

**There is no `claude /login`-style OAuth device flow for DeepSeek anywhere**, official or
reseller. A community plugin marketplace around DeepSeek Harness advertises `dsh-oauth-login` and
similar, but those OAuth into *other* vendors' subscriptions (Claude, Codex, Grok, GLM, Kimi) to
drive them through the DeepSeek CLI. They do not unlock a DeepSeek subscription, because DeepSeek
has none. Unofficial third-party code handling OAuth credentials — do not install on the strength
of a search result.

Also flagged and avoided: `deepseekv4pro.com` sells "DeepSeek coding plans" and is a third-party
reseller, not DeepSeek. Paying it does not upgrade an official DeepSeek account.

**So the decision already taken is the correct one.** The $50/mo Pro tier here is the legitimate
subscription path to DeepSeek-V4-Pro, it has a hard ceiling, and it cannot overspend. The one
constraint to respect is §7 — the key may only be driven through a coding tool.

---


Subscription bought 23/09/2026. Personal, **Pro** tier, $50 USD/month, auto-renewal on.
Account `3004825049` / `phill_mcgurk`. Verified live, not from memory:

```
arkcli plans get   → tier: pro, status: Running
arkcli usage plan  → subscribed: true, session/weekly/monthly all 0%
                     weekly resets 2026-09-28, monthly resets 2026-10-23
```

Re-run those two commands before trusting any number in this file. Everything below that
could change was read from BytePlus's own docs on 23/09/2026 and is dated for that reason.

---

## 1. The three base URLs. One of them bills you outside the plan.

| URL | Effect |
|---|---|
| `https://ark.ap-southeast.bytepluses.com/api/coding` | Anthropic protocol. **Consumes plan quota.** |
| `https://ark.ap-southeast.bytepluses.com/api/coding/v3` | OpenAI protocol. **Consumes plan quota.** |
| `https://ark.ap-southeast.bytepluses.com/api/v3` | **Does NOT consume plan quota. Bills pay-as-you-go.** |

BytePlus, verbatim, repeated on three separate pages:

> "Do not use the Base model URL (`https://ark.ap-southeast.bytepluses.com/api/v3`). Requests
> sent to this Base URL do not consume your Coding Plan quota and will instead incur
> additional charges."

The wrong URL answers normally. Nothing fails. You find out on the invoice.

**Protocol → tool:** Anthropic (`/api/coding`) is Claude Code only. Everything else —
OpenCode, OpenClaw, TraeCode, Hermes Agent, Codex CLI, Cline, Cursor, Kilo Code, Roo Code —
uses OpenAI (`/api/coding/v3`).

## 2. Quota is counted in model INVOCATIONS, not prompts

This is the number that actually matters, and it is the one people get wrong.

> "The estimated request count refers to the expected number of model invocations. In
> practice, a single user prompt often triggers multiple model invocations, and each
> invocation consumes quota as one request."
>
> - Simple Q&A / code generation: **5–15 calls per prompt**
> - Refactor / complex task: **15–30+ calls per prompt**

So a Pro allowance of ~9,500 per 5 hours is roughly **300–600 real prompts**, not 9,500.

**The two BytePlus pages disagree on the numbers.** Use the newer one; both say "approximately".

| Pro tier | per 5 hours | per week | per month |
|---|---|---|---|
| Overview page, updated 2026-09-17 (**use this**) | ~9,500 | ~60,000 | ~120,000 |
| FAQ page, updated 2026-08-31 (stale) | ~6,000 | ~45,000 | ~90,000 |

Resets: 5-hour is a **sliding window** from the first request. Weekly resets **Monday
00:00:00**. Monthly resets on the first day of the subscription month. Exhaustion is a hard
stop — "Exceeding the quota will not consume other packages or your account balance."

Marketing correction: the "3×" figure is **3× Claude Pro** (not Max), and it describes
**Lite**, not Pro. Pro is 5× Lite.

## 3. DeepSeek-V4-Pro carries a quota penalty nobody has quantified

The model this plan was bought for comes with two warnings from BytePlus:

> "DeepSeek-V4-Pro has a **relatively high quota deduction coefficient and consumes quota
> quickly**. It is recommended for difficult and complex problems; for everyday use,
> switching to another model is recommended."

> "DeepSeek-V4-Pro is an **early-access preview version**. If you encounter access congestion
> or frequent rate limit errors, it is recommended to switch to another model."

**So the ~9,500/5h figure does not apply to it, and the coefficient is not published.**
Treat DeepSeek-V4-Pro as the expensive tool reached deliberately, and measure real
consumption with `arkcli usage plan` before and after a run rather than assuming.

`dola-seed-2.0-code` (`seed-2-0-code-preview-260328`) is the everyday coding model.

## 4. Model IDs — config string vs CLI id

The config files want the **short name**. `arkcli plans model-list --plan coding-plan`
returns the **dated id**. They are not interchangeable.

| Config string | arkcli model_id | Context | Max output |
|---|---|---|---|
| `deepseek-v4-pro` | `deepseek-v4-pro-260425` | 1024k | 384k |
| `deepseek-v4-flash` | `deepseek-v4-flash-260425` | 1024k | 384k |
| `dola-seed-2.0-code` | `seed-2-0-code-preview-260328` | 256k | 32k |
| `dola-seed-2.0-pro` | `seed-2-0-pro-260328` | 256k | 32k |
| `dola-seed-2.0-lite` | `seed-2-0-lite-260428` | 256k | 32k |
| `glm-5.2` | `glm-5-2-260617` | 1024k | 128k |
| `glm-5.3-flash` | `glm-5-3-flash-260828` | 1024k | 128k |
| `glm-5.1` | `glm-5-1-260408` | 200k | 128k |
| `kimi-k2.5` | `kimi-k2-5-260127` | 256k | 32k |
| `gpt-oss-120b` | `gpt-oss-120b-250805` | 256k | 32k |
| `bytedance-seed-code` | `seed-1-6-code-preview` | 1024k | 65k |

`ark-code-latest` is a console-managed alias; switching its target takes 3–5 minutes to
apply. **The plan currently routes on `auto`**, which picks a model for you — fine for
interactive work, wrong for a review lane, where a verdict must name the model that produced
it. Pin it with `arkcli plans model-apply`.

**Cursor naming conflict:** if `glm-5.2` / `glm-5.3-flash` / `kimi-k2.5` are rejected, use
`glm-5-2` / `glm-5-3-flash` / `kimi-k2-5`.

## 5. Two quota leaks that are silent by default

**Claude Code telemetry.** BytePlus, verbatim:

> "`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` disables Claude Code's background anonymous
> telemetry requests. **By default these requests go through `ANTHROPIC_BASE_URL` and consume
> Coding Plan quota**; setting it to `"1"` prevents silent quota consumption."

**The embedding model.** "As with other models, the Embedding model consumes plan quota based
on the number of model calls."

## 6. OpenCode — the sanctioned vehicle for a review lane

`npm install -g opencode-ai`, config at `~/.config/opencode/opencode.json`.
Responses API is recommended by BytePlus "for better reasoning quality".

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "byteplus-plan/deepseek-v4-pro",
  "provider": {
    "byteplus-plan": {
      "npm": "@ai-sdk/openai",
      "name": "BytePlus (Responses API)",
      "options": {
        "baseURL": "https://ark.ap-southeast.bytepluses.com/api/coding/v3",
        "apiKey": "<resolved from BYTEPLUS_CODING_KEY, never inlined>"
      },
      "models": {
        "deepseek-v4-pro": {
          "name": "deepseek-v4-pro",
          "limit": { "context": 1024000, "output": 65536 }
        }
      }
    }
  }
}
```

Gotchas, verbatim from the doc:

- "Under `provider.byteplus-plan.models`, **two locations** (the object key and the `name`
  field) must be replaced with the same Model Name. Do not miss either one."
- "`gpt-oss-120b` only supports **Chat API**. Do not add it to the Responses API configuration."
- 1M context is set by `limit.context: 1024000` — **no `[1m]` suffix**, unlike Claude Code.
- `@ai-sdk/openai` appends `/responses`; `@ai-sdk/openai-compatible` appends `/chat/completions`.

## 7. THE HARD BOUNDARY — stated three times, names account suspension

> "**Not available for API calls.** … Using the Coding Plan–provided Base URL and API key
> outside AI coding tools may be identified as **abuse or a policy violation, which could
> result in subscription deactivation or account suspension**."

Enforced as data, not prose: `lane_registry.py` carries `api_calls_forbidden` on the deepseek
lane and `refuse_route()` refuses the direct-API route while allowing the same lane through
its tool. Both behaviours are covered by a control watched firing.

**Nuance worth knowing:** `Hermes Agent` IS on BytePlus's supported-tools list, so Hermes
*as a coding agent* is sanctioned. That does not license pointing the estate's Hermes gateway
— a general API caller — at this endpoint. The banned pattern is the credential leaving a
coding tool, not the product name.

Also: "Other models cannot be used in the Coding Plan." And the plan is "primarily intended
for individual developers"; team collaboration is meant to go through pay-as-you-go.

## 8. What the docs do NOT tell you

Established by grep across all five decoded pages, with a positive control proving the search
returns hits:

1. **No numeric RPM / TPM / concurrency limit anywhere.** Only qualitative claims ("TPM fits
   day-to-day development workloads", "the Pro plan offers higher TPM limits").
2. **No prices** on any of the five pages.
3. **No value for the DeepSeek-V4-Pro deduction coefficient** — warned about, never quantified.
4. **Which quota table is authoritative** — BytePlus has not reconciled its own two pages.

## 9. Claude Code — the config, and why this estate must not use it

Recorded so nobody has to go looking, and so the hazard is written down next to it.

```json
{ "env": {
    "ANTHROPIC_AUTH_TOKEN": "<ARK_API_KEY>",
    "ANTHROPIC_BASE_URL": "https://ark.ap-southeast.bytepluses.com/api/coding",
    "ANTHROPIC_MODEL": "<MODEL_NAME>",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
} }
```

**Do not apply this to `~/.claude/settings.json` on any machine in this estate.** Those two
variables move every Claude Code session off the Max subscription. `arkcli helper configure
claude-code` writes exactly this file. The Codex equivalent is safer by default — it writes
`~/.codex/arkcli.config.toml` unless you pass `--codex-config-scope global`.

1M context for Claude Code needs BOTH `"ANTHROPIC_MODEL": "deepseek-v4-pro[1m]"` and
`"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"`.

## Sources

Fetched 23/09/2026. `WebFetch` returns nothing useful on these pages — the body ships as
escaped JSON inside a `<script>` tag, so fetch with `curl` and decode `MDContent`.

- `docs.byteplus.com/en/docs/ModelArk/1925114` — overview, quota, terms
- `docs.byteplus.com/en/docs/ModelArk/2165245` — FAQ, quota (stale table)
- `docs.byteplus.com/en/docs/ModelArk/2188959` — tools index, Cline/Cursor/Kilo/Roo setup
- `docs.byteplus.com/en/docs/ModelArk/2188958` — OpenCode
- `docs.byteplus.com/en/docs/ModelArk/1928262` — Claude Code
- API keys: `ai.byteplus.com/ark/region:ap-southeast-1/apikey`
