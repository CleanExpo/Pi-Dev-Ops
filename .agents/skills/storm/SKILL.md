---
name: storm
description: Use when the user wants a comprehensive, neutral, citation-grounded article, report, briefing, or explainer researched from scratch on a topic — invoked as /storm or by asking to "STORM" a topic. Reproduces the Stanford STORM method (perspective discovery + retrieval-grounded multi-perspective Q&A → outline → grounded long-form write-up). Not for quick factual lookups, opinion pieces, or topics that need private/internal data.
---

# STORM — Multi-Perspective, Retrieval-Grounded Article Generation

Reproduces Stanford's **STORM** (Synthesis of Topic Outlines through Retrieval and Multi-perspective question asking) as a runnable pipeline using Claude Code's own tools — there is no external model to install.

**Core principle:** Do **not** write-then-cite. First *research like a panel of experts*: discover diverse perspectives, then have each perspective interrogate the topic in conversations grounded in **live web retrieval**, collecting cited evidence. Only after the evidence exists do you build a reference-backed outline and write the article section-by-section with inline citations. Grounding precedes prose, always.

## When to use
- A from-scratch overview / report / briefing / explainer / literature-style survey on a topic.
- Output should be **neutral, structured, and every non-obvious claim cited** to a real source.

## When NOT to use
- Quick factual lookups → just answer (or use a single web search).
- Opinion/persuasion pieces, marketing copy → STORM aims for neutral synthesis.
- Topics requiring private/internal/proprietary data → STORM is web-retrieval grounded; say so.
- The user wants a fast, shallow scan → use the `deep-research` skill instead if multi-source fact-checking with a verify pass is the goal; use STORM when *breadth of perspective* and a structured article are the goal.

## Args
`/storm <topic or question>` — the topic is the argument. If the topic is underspecified (missing scope, audience, region, time-frame, or angle), ask **2–3 tight clarifying questions first**, then proceed. Don't research a vague topic.

## Pipeline — follow in order

### 1. Scope
Restate the topic in one sentence: subject, intended depth, audience, and any boundaries (time period, geography, sub-aspects in/out). Pick a target length band (e.g. short brief ≈ 600–900 words; full article ≈ 1500–3000+). Confirm only if genuinely ambiguous.

### 2. Discover perspectives (the STORM differentiator)
Identify **3–5 distinct perspectives** from which a thorough treatment must be examined — e.g. a domain practitioner, a skeptic/critic, an end-user/affected party, a historian/origins angle, an economics/policy angle, a technical-internals angle. For each: a short role label + the 2–4 questions that perspective most cares about. Diversity here is what makes the final article comprehensive rather than one-sided. (Optionally seed perspectives by first skimming 1–2 high-level sources / related topics.)

### 3. Multi-perspective grounded Q&A — the core loop
For **each perspective**, simulate an expert conversation:
- The perspective asks a question.
- An "expert" answers **only from retrieved sources** — use `WebSearch` to find sources and `WebFetch` to read them; never answer from memory.
- Capture each answer as a claim **paired with its source URL + title**. Follow-up questions should dig into gaps, disagreements, and specifics (numbers, dates, named entities), 3–5 turns per perspective.

**Run perspectives concurrently with subagents.** Dispatch one subagent per perspective (Agent tool, `Explore`/`general-purpose`), each instructed to do its own `WebSearch`/`WebFetch` Q&A and **return structured findings: a list of `{claim, sourceUrl, sourceTitle, perspective}`**. This is the big context/time saver. For large topics, the `Workflow` tool can pipeline discover→Q&A→verify, but plain parallel subagents are the default.

### 4. Curate references + build the outline
Pool all findings. **Deduplicate** overlapping claims, **cluster** by theme, and **reconcile conflicts** (note disagreements explicitly rather than picking silently). Assign each surviving source a citation number `[1], [2], …` in a reference map. Then generate a **hierarchical outline** (sections → subsections) driven by the clustered evidence — the outline must be coverable by the references you actually have, not aspirational.

### 5. Write the article — section by section
Write each section grounded in its clustered evidence, with **inline numbered citations** `[n]` after every non-obvious claim. Open with a short lead/summary paragraph (Wikipedia-style). Keep tone **neutral and encyclopedic**; attribute opinions ("Critics argue…[4]"). Do not introduce claims that aren't in the collected evidence — if a section is thin, go back to step 3 and gather more rather than inventing.

### 6. Polish + reference list
Consistency pass (terminology, no duplicate facts across sections, citations resolve), tighten the lead, then append a **"References"** list mapping each `[n]` → title + URL. Optionally add an "Open questions / contested points" section for unresolved conflicts.

## Quality bar
- Every non-obvious claim carries an inline citation to a **real, fetched** source (no fabricated/guessed URLs).
- ≥ 3 perspectives genuinely represented; the article isn't single-voiced.
- Conflicts surfaced, not hidden. Neutral tone. No invented facts.
- References section resolves 1:1 with inline markers.

## Output
Deliver the finished article (Markdown, with inline `[n]` citations + References list) as the response. If the user asked for a file, write it; otherwise inline. State the perspective set used and the source count up front.

## Common mistakes
| Mistake | Fix |
|---|---|
| Writing from memory, citing afterward | Retrieve first (step 3); prose only from collected evidence. |
| One perspective dominates | Enforce 3–5 distinct perspectives in step 2; one subagent each. |
| Sources guessed/hallucinated | Only cite URLs actually fetched via WebFetch. |
| Skipping the outline | Build the reference-backed outline (step 4) before writing. |
| Conflicts silently resolved | Note disagreements explicitly with both sources. |
| Doing it all in one context | Fan out step 3 to parallel subagents that return structured findings. |

## Fidelity note
This maps STORM's stages — perspective discovery, perspective-guided question asking, retrieval-grounded answering, information curation, outline generation, and article generation — onto Claude Code (WebSearch/WebFetch = retrieval; subagents = the conversational agents; synthesis = curation/writing). It is the *method*, not the Python package.
