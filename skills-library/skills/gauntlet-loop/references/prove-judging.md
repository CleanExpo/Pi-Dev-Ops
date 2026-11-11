# Prove mode — judging, domains and sample size

Adapted from `prove-it-better` (MIT, Hamish Davison; see `../LICENSE-prove-it-better`).

## Contents
- [Writing criteria](#writing-criteria)
- [The judge prompt](#the-judge-prompt-what-scriptsprove_judgepy-sends)
- [Bias controls](#bias-controls)
- [Sample size and reading results](#sample-size-and-reading-results)
- [Reading the judge's reasons](#reading-the-judges-reasons)
- [Choosing the judge model](#choosing-the-judge-model)
- [Applying the method beyond AI features](#applying-the-method-beyond-ai-features)

## Writing criteria

Criteria describe how well the output does its **job**, not how it sounds. Three to five, each one checkable by a careful reader with the context in front of them.

| Job | Good criteria | Weak criteria |
|---|---|---|
| Topic ideas for a business | Fits what the business actually sells; tied to real searches; no repeats | Creative; engaging |
| Landing page | Accurate (nothing invented); would convert the stated audience; follows the brief | Well written |
| Support reply | Resolves the issue; correct policy; tone fits the customer | Friendly |
| Statistics for an article | Relevant to the topic; from the right market; sourced and checkable | Interesting |

Write one sentence per criterion saying what a winner does. Include "nothing invented" whenever the output makes factual claims.

## The judge prompt (what `scripts/prove_judge.py` sends)

- The task: one sentence on the job the output must do.
- The context the output was produced from (the real input, the source material).
- The criteria.
- Output A and Output B, unlabelled as old/new.
- Instructions: judge each criterion A / B / tie with a one-line reason; give an overall verdict; list concrete defects in each output; do not reward length; facts in the context beat claims in the output; trust any "AUTOMATED CHECK" line over your own impression.

## Bias controls

| Bias | Control |
|---|---|
| Position (prefers first or second) | Judge every pair twice with the order swapped; count only agreeing verdicts |
| Self-preference (a model favours its own family) | Judge from a different vendor than every contestant; otherwise hard checks only |
| Author bias (you built the challenger) | You never judge; you only read the judge's reasons |
| Length | Instruction not to reward length; check that winners are not just longer |
| Surface polish over substance | Hard checks for facts, links, numbers; put results in front of the judge |

## Sample size and reading results

- Fewer than ~8 cases: treat any result as a hint, not a verdict.
- 10–12 real cases with a lopsided result (10–0, 11–0) is strong evidence.
- Close results (6–4, 5–3–4) are noise until confirmed on more cases.
- Always confirm a win on a **fresh** sample before shipping; the first sample is the one you tuned on.
- Ties are information: many ties usually means the criteria do not separate the outputs — sharpen them.

## Reading the judge's reasons

The defect lists are the most valuable output. Group them across cases; the top two or three repeated defects are the next iteration. Fix those specifically, rerun, repeat.

## Choosing the judge model

Use the strongest model available from a vendor that produced neither output. Estate work is
usually built by Claude, so the default judge is non-Anthropic: `--provider openrouter` with a
free model (OpenRouter is the estate's free-model harness; `OPENROUTER_API_KEY` is read from the
environment, then `~/.hermes/.env`). `--provider openai` and `--provider anthropic` remain for
contestants from other vendors. `--provider mock` returns fixed verdicts for testing the pipeline
only and never counts as evidence.

## Applying the method beyond AI features

The phases never change. What changes is the judge, the hard checks, and what "live" means.

| What you are improving | Real cases | Judge | Hard checks | Live verdict |
|---|---|---|---|---|
| AI feature / agent / prompt / model swap | Real production inputs | Blind pairwise model judge, other vendor, both orders | Links load, quotes appear in source, facts match, cost per run, latency, schema valid | Usage, complaints, retries, regenerations |
| Email / subject line | Past campaigns and their results | Blind judge as pre-screen only | Offer valid, links work, no broken merge fields, no claim you cannot back | Open and click rate vs past sends of the same genre |
| Landing / pricing page | Real traffic, past copy, objections from sales and support | Blind judge as pre-screen only | Prices match checkout, page speed, mobile layout, accessibility | A/B test on conversion — check traffic is enough to reach a result first |
| YouTube titles / thumbnails | Your past videos and their CTR | Blind judge as pre-screen only | Title length, readability at small size | Platform test-and-compare CTR, then watch time |
| Code change / performance | Real workloads and inputs | Usually none | Test suite, benchmarks on real inputs, error rate, memory | Production latency and error dashboards |
| Cost / cloud bill | Real invoices and usage line items | None | $ per month per line, latency, error rate, availability, backups | Next invoices vs baseline |
| Support / sales process | Real past tickets or calls | Blind judge on reply quality | Policy correct, resolution time, refund accuracy | Resolution rate, CSAT, conversion |

### Notes per domain

- **Behaviour outcomes** (opens, clicks, sign-ups, revenue): the model judge is a cheap filter so you only spend real traffic on strong candidates. The live number decides.
- **Slow feedback** (SEO rankings, retention): decide on hard checks and leading indicators, ship reversibly, and schedule the real-world check for when the data can exist.
- **Costs**: start from the real invoice, not a usage estimate. Seats, other projects on the same account and duplicate charges often matter more than any optimisation.
- **Copy and marketing claims**: every number in the copy must come from a measurement; the render or review step should check for invented deadlines, prices that differ from checkout, and broken personalisation.
- **No current version** (a brand-new thing): compare two or more candidates against each other with the same blind method, then compare the winner against the user's stated bar.
