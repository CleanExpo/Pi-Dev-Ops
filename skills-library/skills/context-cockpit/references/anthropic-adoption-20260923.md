# Anthropic prompting guidance — what this estate adopted, and what it refused

Source: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1`
Read and triaged 23/09/2026. Re-read the source before trusting this file; it is a record of a
decision, not a copy of the doc.

## The trap this file exists to avoid

The doc is written for **Claude Fable 5.1 and Mythos 5.1**. The harness that triaged it runs
**Opus 5**. `CLAUDE.md` already records why that distinction matters: `FABLE_PLAYBOOK.md` was
written to make gpt-5.5 imitate Fable 5, and its always-load import was removed on 29/07/2026
because Anthropic's own Opus 5 migration guidance says carrying that scaffolding forward is
actively harmful — it causes over-verification in a model that already verifies its own work.

So nothing here was pasted in because Anthropic wrote it. Each item was tested against two
questions: **is it model-specific or harness-level**, and **does this estate already do it**.
A rule the estate already enforces is not adopted twice. `CLAUDE.md` loads on every task, and
a duplicated rule costs context on every task forever.

Two searches grounded the "already does it" answers: `claude-fable-5-1` and `mythos` appear in
exactly two tracked files estate-wide, both as prose rather than as a live model id, so no
harness here actually dispatches to a Fable model today.

## The triage

| Section | Verdict | Where it landed, or why not |
|---|---|---|
| **Consider all effort levels** | REJECT | Effort is an API parameter. Claude Code does not expose it per-turn the way the doc assumes, and the estate's routing decisions live in `model-routing-claude-first` and `/context-cockpit`. Adopting a sweep we cannot run would be doctrine that cannot be checked. |
| **Ask for user-facing progress updates** | REJECT | Already in force and stronger. The harness instructs brief updates between tool calls, and the communication contract bans trailing summaries the founder did not ask for. The doc's fix is for harnesses whose prompts suppress narration; this one does the opposite. |
| **Batch independent tool calls in agent loops** | REJECT | Already in force verbatim: the harness instructs that independent calls go in one block, and the Decision-Rights Matrix reinforces it. |
| **Keep the conversation history append-only** | REJECT | Applies to code that builds a `messages` array against the API. This estate consumes a harness rather than building one. Relevant only if Pi-Dev-Ops or Hermes starts calling the Messages API directly, at which point re-read it. |
| **Writing density** | **ADOPT** | `skills/unslop/SKILL.md`, as pattern 32, "Mannered prose". Its 31 existing patterns covered metaphor *nouns* (26) and feeling-words (27) but not the general substitution of flourish for direct statement. Net-new. |
| **Formatting in chat** | REJECT | Already in force and the estate leans further. The communication contract mandates headed sections, bullets, numbered steps and tables, citing `founder-style-listicles`. No anti-formatting language exists here to remove. |
| **Quoting retrieved sources** | REJECT, and this is the one real gap left open | The estate gates *substantiation* through `claim-verifier` and `nexus-copywriter`, but nothing marks reproduced source wording as a quotation. The right home is `nexus-research` / `nexus-extract`, and changing those needs its own contract rather than a drive-by edit. Named here so it is not lost. |
| **Finish the whole task** | REJECT | Already in force, and the estate got there first. The Decision-Rights Matrix bans "Want me to…", "Should I…", "Shall I…" by name; `CLAUDE.md` §7 mandates continuous autonomous operation; `operating-style-1-and-done` records the founder's stated #1 frustration as stopping and re-stopping. The doc's block would restate all of it. |
| **Tell the model what to preserve in compaction summaries** | **ADOPT** | `skills/session-handoff/SKILL.md`. The estate's handoff IS its compaction, and the doc's six-item list is more exacting than what the skill asked for — in particular preserving the user's own words and details that are hard to reconstruct. Net-new. |
| **Keep changes and tests to what the task asks for** | **ADOPT** | `CLAUDE.md` §3. §3 already said not to improve adjacent code, but said nothing about *tests*: how many to commit, sized against what, and that scratch checks must not graduate into permanent test files. Net-new, and it bites here — this estate over-produces controls. |
| **Search triggering at low effort** | **ADOPT** | `CLAUDE.md` §0, beside the negative-claim rule. The estate had the narrow case (`never-quote-a-lane-or-quota-from-memory`); the doc generalises it to any fast-moving name. Adopted as a principle, not as the doc's prompt block. |
| **Reduce safeguard false positives** | REJECT | Three API-level tips (compile-check phrasing, obscure languages, base64 in tool output). Nothing in this estate returns `stop_reason: "refusal"` today. Adopting it would be doctrine for a problem not observed here. |
| **Prefer targeted edits over whole-file rewrites** | **ADOPT** | `CLAUDE.md` §3. The estate stated no preference between `Edit` and `Write` anywhere. Net-new, and it is pure cost: a rewrite of a long file burns output tokens and wall-clock for an identical result. |
| **Leave room for long outputs at xhigh and max effort** | REJECT | Depends on setting `max_tokens` and effort per request, which this harness does not expose. Same reasoning as effort levels. |
| **Let the lead agent keep working while subagents run** | REJECT | Already true structurally: the `Agent` tool runs subagents in the background by default and re-invokes on completion, which is precisely the shape the doc asks harness authors to build. `persistent-subagents` covers the resume half. |
| **Give vision work tools to crop and zoom** | REJECT | Worth doing, but it is a tool to build (a crop-and-enlarge tool over an image), not a prompt rule to write. Recorded as a build task rather than adopted as doctrine. |

## Score

Five adopted, eleven refused. Nine of the eleven were refused because this estate already
enforced the behaviour, which is the useful finding: the harness had independently converged on
most of Anthropic's guidance, and the gaps were narrow and specific.

Two were refused as genuine follow-ups rather than as "already done":
- quotation-marking in `nexus-research` / `nexus-extract`
- a crop-and-zoom tool for chart and dense-image work
