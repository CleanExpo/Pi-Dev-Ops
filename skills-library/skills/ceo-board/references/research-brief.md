# Stage 1.5 — Research Brief (full method)

The conditions for running/skipping Stage 1.5 and the fast-vs-deep selection live in `SKILL.md`.
This file holds the full method for both modes, the JSON contract, and the hard rules.

## Mode selection (RA-1974)

- **`fast` (default)** — general-purpose subagent with WebSearch + WebFetch, 300s budget. Use for most briefs.
- **`deep`** — invoke `mcp__margot__deep_research_max` for Gemini-backed multi-source research with corpus grounding. Use when the brief contains the tag `[deep-research]` (anywhere in the brief), or when the founder explicitly says "deep research first" / "use Margot" / "deep research". Budget: **1200s wall-clock**; the CEO polls every 30s while waiting and shows a progress line each poll.

If `deep` mode is requested but the `mcp__margot__deep_research_max` tool is not available in this session (Margot MCP not connected), fall back to `fast` mode and emit one line in chat: *"Margot MCP not connected — falling back to fast research."* Do not stall.

## Method (fast)

1. The CEO emits 2–5 sharp empirical questions the board needs answered. Format each as a single sentence ending in `?`. Bad: "research the market". Good: "What is Acme Restoration's published mid-market pricing as of 2026-Q2?"
2. Dispatch a single research subagent via the `Agent` tool with `subagent_type: general-purpose`. Time budget: **300 seconds**. Pass the agent the question list verbatim plus the line: *"Return a JSON brief matching the schema below. Each finding cites ≥1 source URL with a fetched-date. Do not invent claims; mark unverifiable as open_questions."*
3. The subagent returns a JSON brief matching the contract:

   ```jsonc
   {
     "research_required": true,
     "questions": ["..."],
     "findings": [
       { "question": "...", "claim": "...", "confidence": "high|medium|low",
         "sources": [{ "url": "...", "title": "...", "fetched": "YYYY-MM-DD", "excerpt": "..." }] }
     ],
     "open_questions": ["..."],
     "completed_at": "ISO-8601",
     "cost_seconds": 47
   }
   ```

4. The CEO inlines the brief into the chat verbatim under the heading `## RESEARCH BRIEF (Stage 1.5)`. This is what the personas will see in Stage 3.
5. **If research fails or runs out of budget**, the brief still emits with `research_required: false` and a `failure_reason` field. Stage 2 proceeds. Honest failure: never silently skip — name what couldn't be answered.
6. **Hard rules:**
   - Every claim has ≥1 source URL with a fetched-date. No source → finding is dropped, surface as `open_question`.
   - `confidence: low` claims are kept and flagged. The Contrarian will pressure-test them in Round 2.
   - If the brief was tagged `[no-research]`, emit a single line: *"Stage 1.5 skipped per founder tag."* and proceed.

## Method (deep — Margot)

1. The CEO emits 2–5 sharp empirical questions exactly as in `fast` mode.
2. Concatenate the questions into a single `topic` string suitable for Margot. Format: *"Research the following for a strategic board decision: 1) <question 1> 2) <question 2> ... For each question, cite primary sources where possible."* (Margot expects a research brief, not a bare question list.)
3. Call `mcp__margot__deep_research_max(topic=<concatenated>, use_corpus=true)`. Receive `{interaction_id, status: "processing"}` immediately. Emit one line in chat: *"Margot dispatched (interaction_id=...). Polling every 30s; budget 1200s."*
4. **Poll loop**: every 30 seconds, call `mcp__margot__check_research(interaction_id=<id>)`. Continue until `status` is `completed`, `failed`, or 1200s elapsed. Emit a one-line progress note per poll (*"poll N — status: processing / Ns elapsed"*).
5. **On completion**: transform Margot's report + citations into the same JSON brief contract (questions / findings / sources / open_questions). Split the report into per-question findings — section headers in Margot's output typically map 1:1 to the input questions. Each finding inherits the full citations array. Set `mode: "margot"` and `confidence: "high"` by default (Margot's depth justifies it; downgrade specific findings to medium/low only if the report itself flagged uncertainty).
6. **On timeout** (1200s exceeded): emit `research_required: false` with `failure_reason: "Margot exceeded 1200s budget; interaction_id: <id>; check status manually via mcp__margot__check_research"`. Stage 2 proceeds without the deep brief. Do not block the board.
7. **On Margot failure** (status=`failed` or error returned): emit `research_required: false` with the error; offer to fall back to `fast` mode (founder can say "fall back" to retry).
8. Inline the brief into the chat under `## RESEARCH BRIEF (Stage 1.5, deep)`.

The hard rules from the fast path apply identically — every claim cites a source URL with fetched-date; sourceless findings drop to `open_questions`.

## How the brief feeds the debate

**The brief becomes mandatory Stage 2 input.** When the CEO frames the real question and identifies fault lines in Stage 2, they cite specific findings by question number ("Per finding #2, …"). When the Contrarian challenges in Round 2, they call out claims as "research-backed" or "speculative — no source surfaced". Personas reference findings by their question number throughout.
