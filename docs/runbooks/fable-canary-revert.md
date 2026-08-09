# Fable-5 Adversary Canary — Flip / Revert Runbook (RA-1099 Wave 3)

The canary runs `claude-fable-5` on the pre-push **adversary** review role only.
The switch is a single env var. `.harness/config.yaml` keeps adversary on `opus`,
so both flip-on and revert are env-only — **no code redeploy**.

## Flip ON (start the 7-day canary)
Set on the Railway backend service, then restart it (env change = restart, not
rebuild): `TAO_FABLE_ALLOWED_ROLES=adversary`. Effective model then resolves to
`claude-fable-5` for the adversary role only; all other roles are unaffected.

## Revert (kill switch)
`railway variable delete TAO_FABLE_ALLOWED_ROLES -s Pi-Dev-Ops` (verified 2026-07-05),
then the service restarts. Adversary immediately returns to `opus` (the committed
default). No code change, no rebuild. NOTE: `railway variables --set
TAO_FABLE_ALLOWED_ROLES=` (set-empty) is a **no-op** — Railway keeps the prior value;
you MUST use `variable delete`. Rehearsed revert (delete → confirm gone → re-set)
executed 2026-07-05 and confirmed working.

## Kill-threshold — amplification
Kill the canary if billed output tokens per 1K visible chars on adversary runs
exceeds **~1100 tok / 1K chars**. Read `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`:
each `"phase":"adversary"` row carries `output_tokens` (billed) and `output_len`
(visible chars); amplification = `output_tokens / (output_len/1000)`. Rows with
`"model":"claude-fable-5"` are canary runs; `error":"refusal"` flags a decline.

## Model-unavailability / refusal behaviour
A fable refusal (`stop_reason=="refusal"`) or any fable error auto-retries the
SAME review once on `claude-opus-5` (`app/server/session_sdk.py`
`_run_claude_via_sdk`), so the gate never silently passes an errored/refused
review. A fallback run writes two metric rows (fable failure + opus retry). Unset
the env var to make opus the permanent default again.

## Ships OFF by default
`TAO_FABLE_ALLOWED_ROLES` is empty by default (`app/server/config.py`) — the
canary is OFF until the var is set.
