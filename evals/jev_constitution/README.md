# Jev constitution eval

Measures how well TypeSafe Jev answers yes/no compliance questions drawn from the
Unite-Group Nexus Constitution (which also governs RestoreAssist), before Jev is
trusted with any real decision.

This is an eval, not a routing lane. `app/server/provider_policy.py` still refuses
metered providers, and nothing here changes that. Do not "fix" the refusal to make
this run: this runs as its own script.

## Pieces

| File | What it holds |
|---|---|
| `questions.json` | One Noul question per binding constitutional rule, with its quote and `source` (file:line) at Unite-Group `origin/main` `8eb9491b8`. `quote_verbatim` is set by `quotes.py`, never by hand: true when every fragment of the quote (split on `...`, `…` or a flattened list marker ` * `) appears in order, word for word, in that file. 538 of 538 on 2026-09-29 |
| `quotes.py` | Re-derives `quote_verbatim` from a Unite-Group clone: `--repo ~/Unite-Group` checks (exit 1 on any stale flag), `--write` records |
| `cases/<question-id>.jsonl` | The labelled scenarios for that question |
| `generate.py` | Writes cases with Claude (Max plan), has Codex (Pro plan) label them blind, keeps only agreements |
| `harness.py` | `validate` checks every case set; `run` asks Jev and scores it |
| `results/` | One JSON report per run |

## Rules a case set must meet before it is scored

- at least 1000 cases, each with matching Claude and Codex labels
- no duplicate scenarios
- each answer (complies / violates) is 30-70% of the set
- at least 50 cases in each of Jev's documented weak spots: arithmetic, dates,
  indirection, irrelevant context, adversarial wording

A question that misses any of these, or whose quote is not verbatim, is reported as
REFUSED, never scored.

## Running it

```bash
# 1. build cases for one question (subscriptions only, no API key read)
.venv/bin/python -m evals.jev_constitution.generate --question core-01 --target 1100

# 2. check every case set
.venv/bin/python -m evals.jev_constitution.harness validate

# 3. score Jev. Needs TYPESAFE_API_KEY in the environment (Vercel pi-dev-ops holds it)
.venv/bin/python -m evals.jev_constitution.harness run --question core-01
```

`run` exits 2 (BLOCKED) with no key, and 3 if a fake key is not refused with HTTP 401.
Neither case writes a score.

## Cost

Jev input is $0.042 per million tokens. 1000 cases at roughly 600 tokens each is
about 3 US cents per question. Case writing runs on the Claude Max and ChatGPT Pro
subscriptions.

## What a result means

`missed_violations` is the number that matters: Jev said "complies" to a real
violation. A high accuracy with any missed violations on a critical rule means Jev
must not decide that rule alone. Labels come from two models agreeing, not from a
human, so a result is evidence about agreement with Claude and Codex, not proof of
constitutional correctness.
