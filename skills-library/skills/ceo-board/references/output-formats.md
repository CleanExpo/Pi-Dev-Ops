# Output Formats — verbatim stage templates

Read this once before running the deliberation. Each stage in `SKILL.md` produces its output
using the matching template below. Headings and structure are the contract — keep them exact.

## Stage 2 — CEO FRAMES

```
## CEO FRAMES

**The Real Question:** [one crisp sentence]

**Where we'll disagree:**
- [fault line 1]
- [fault line 2]
- [fault line 3]

**Debate parameters:** [constraints + what CEO needs to hear]
```

## Stage 3 — BOARD DEBATES (each round)

```
## ROUND [N] — [ROUND NAME]

**[PERSONA NAME]:** [their contribution]

**[PERSONA NAME]:** [their contribution]
...
```

## Stage 4 — CONSTRAINT CHECK

```
## CONSTRAINT CHECK

**Technical Architect:** [feasibility verdict + any fatal constraints + research-blocking opens]

**Revenue:** [commercial viability verdict + any fatal constraints + research-blocking opens]

**Fatal constraints raised:** [list or "none"]
**Research-blocking opens:** [list or "none"]
```

## Stage 5 — FINAL STATEMENTS

```
## FINAL STATEMENTS

**Revenue:** [one sentence]
**Product Strategist:** [one sentence]
**Technical Architect:** [one sentence]
**Market Strategist:** [one sentence]
**Compounder:** [one sentence]
**Moonshot:** [one sentence]
**Custom Oracle:** [one sentence]
**Contrarian:** [one sentence]
```

## Stage 6 — THE MEMO

The memo is not a summary of the debate. It is a decision. Written in the CEO's voice. Authoritative.

```
═══════════════════════════════════════
THE MEMO
Date: [today]
From: CEO
Re: [the real question, in one line]
═══════════════════════════════════════

DECISION
[State the decision clearly. One paragraph. No ambiguity.]

RATIONALE
[Why this decision. Reference the strongest arguments from the board AND
the strongest research findings. 2-3 paragraphs. Include what made this
hard — acknowledge the real tension.]

THE DISSENT THAT ALMOST CHANGED MY MIND
[Name the board member and the argument that came closest to flipping
the decision. Why it didn't. This matters — it tells the engineer where
the fragility is.]

WHAT WOULD CHANGE THIS DECISION
[2-3 conditions. If any of these prove true, the decision should be revisited.
Tie at least one condition to a Research Brief finding or open_question
where applicable.]

RESEARCH GAPS
[List any open_questions from Stage 1.5 that should be resolved before
the decision becomes irreversible. If Stage 1.5 was skipped, write "N/A —
brief was self-contained / tagged [no-research]". If research failed,
list the failure_reason and what was therefore undecidable.]

NEXT ACTIONS
[3 actions. Owner, timeline, and what "done" looks like for each.
At least one action MUST address the highest-impact RESEARCH GAP if any
exist.]

RISK TO WATCH
[The single most dangerous assumption baked into this decision.]
═══════════════════════════════════════
```
