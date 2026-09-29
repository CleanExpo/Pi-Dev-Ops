# OpenAI GPT-6 family — operating card

Read from OpenAI's own announcement on 23/09/2026:
`https://openai.com/index/introducing-gpt-6-sol-and-luna/`

**Fetching note:** `WebFetch` and plain `curl` both return **HTTP 403** on openai.com. The page
came back through `https://r.jina.ai/<url>`. Use that route, or the page will look absent when it
is merely blocked.

---

## 1. The three models

| Model | API id | Input | Output | Role |
|---|---|---|---|---|
| **GPT-6 Astra** | `gpt-6-astra` | — | — | *"continues to be our best model across the board. Choose it when you want the best results and an uncompromising experience."* |
| **GPT-6 Sol** | `gpt-6-sol` | **$2** / MTok | **$10** / MTok | The workhorse. 50% cheaper than GPT-5.6 Sol. |
| **GPT-6 Luna** | `gpt-6-luna` | **$0.10** / MTok | **$0.50** / MTok | Cheap tier. 50% cheaper than GPT-5.6 Luna. |

Cached input reads are discounted **90%**, and OpenAI says GPT-6 gets *"higher cache hit rates by
default."* That matters here: this estate's own measurement puts ~65% of its Claude bill in cache
reads, so cache behaviour dominates cost on long agent sessions.

## 2. Availability — SUBSCRIPTION, not API credits

Verbatim:

> "GPT-6 Sol and GPT-6 Luna are available in **ChatGPT Work and Codex** starting today for all
> **Plus, Pro, Business, Enterprise, and Edu** users. Free and Go users can access GPT-6 Luna in
> the desktop app. These models are **not yet available in Chat**. In the OpenAI API, they are
> available as `gpt-6-sol` and `gpt-6-luna`."

So the Codex CLI reaches them on the ChatGPT subscription. This satisfies the standing rule that
ChatGPT products run on the paid subscription and never on API credits.

## 3. The CLI must be current or the models do not exist

Measured on this machine, 23/09/2026, with a negative control:

| CLI | `gpt-6-nonexistent-xyz` | `gpt-6-sol` |
|---|---|---|
| **0.153.4** | `400 … model is not supported` | `400 … model is not supported` + `Model metadata for 'gpt-6-sol' not found` |
| **0.156.1** | `400 … model is not supported` | `You've hit your usage limit … try again at Sep 26th, 2026 8:01 PM` |

**The error changing from "not supported" to "usage limit" is the proof the model is reachable.**
A stale CLI reports a brand-new model exactly as it reports a typo, so "not supported" is never
by itself evidence that a model does not exist — check `npm view @openai/codex version` first.

Fix: `npm install -g @openai/codex@latest`.

## 4. Claimed standing against Claude, from OpenAI's own numbers

Vendor-published, uncontrolled, and worth treating as a claim rather than a finding. Recorded
because it drives the routing decision below.

| Benchmark | Claim |
|---|---|
| AutomationBench | Sol (xhigh) **33.2%** at **$0.27**/task vs Claude Opus 5 (max) 26.9% at **11.1×** the cost |
| Agents' Last Exam | Sol (max) **56.4%**, above Opus 5's best, at 60% lower cost/task |
| DeepSWE v1.1 | Sol (max) **68.8%** vs Claude Fable 5 (xhigh) 69.9% — within 1.1pp at ~80% lower cost |
| OSWorld 2.0 | Sol (xhigh) 60.5% vs Opus 5 (medium) 60.3%, ~80% lower cost |
| FrontierCode | Sol *"is able to match Claude Fable 5.1 xhigh at much lower cost"* |

OpenAI's own footnote undercuts one row: the Fable 5.1 datapoint *"understates its actual cost,
as it omits the cost of the Opus 5 fallbacks, which occurred on ~40% of tasks."*

## 5. How this estate routes them

`~/.codex/config.toml` sets `model = "gpt-6-astra"`, `model_reasoning_effort = "medium"`. That is
the right default for interactive founder work and the **wrong** default for automated review —
every bulk review would spend Astra quota from the same shared ChatGPT envelope.

**Changed 23/09/2026:** `independent_review.py` pins the codex review lane to `gpt-6-sol` via
`CODEX_REVIEW_MODEL`, leaving the account default untouched. Set `CODEX_REVIEW_MODEL=` (empty) to
fall back to the account default.

Why this is safe rather than a silent downgrade: an unknown model id is refused **at the API**
with `model is not supported when using Codex with a ChatGPT account`, which fails the lane
loudly. It cannot quietly resolve to something cheaper.

## 6. Live state worth re-checking before trusting

- **Codex quota was exhausted on 23/09/2026, resetting `Sep 26th, 2026 8:01 PM`.** Quota is
  account-level, not per-machine, so all three computers share it.
- Astra effort is `medium`. The benchmark claims above are at `xhigh`/`max`; a medium-effort
  comparison is not the one OpenAI published.
- "Not yet available in Chat" may have changed. Re-read the announcement rather than assuming.
