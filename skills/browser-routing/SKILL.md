---
name: browser-routing
description: Use when a task needs a browser — automating a web flow, reviewing or improving UI, debugging a page, recording evidence, or QA-testing a deploy — before picking a browser tool or writing a browser-touching skill.
---

# browser-routing — one router for every browser surface

Four browser surfaces are installed. Pick by job, not by habit; using the wrong one wastes
turns (e.g. driving login flows through raw CDP, or running Lighthouse through the extension).

## Route by job

| Job | Surface |
|---|---|
| Logged-in flows in the user's real session, visual UI review, forms, GIF evidence recordings | **claude-in-chrome extension** (invoke the `claude-in-chrome` skill first, then the MCP tools) |
| Lighthouse audits, performance traces, console/network debugging, heap snapshots | **chrome-devtools MCP** |
| Mechanical scripted automation where no visual judgment is needed | **`browser-harness`** (CDP into running Chrome) |
| PASS/FAIL QA coverage of a deploy or feature | **`vibetest`** |

Wrong-machine binding or a fresh session that must control this Mac's Chrome → run
`bind-chrome` first.

- **Completion criterion:** one surface chosen and named before the first browser tool call.

## The UI-improvement loop

For any "improve/fix/review this UI" task, run the evidence loop — it satisfies
read-before-edit, test-after-edit, and grounded-progress-claims in one motion:

1. Navigate to the live page → screenshot (the **before**).
2. Critique against the brand/design system (BrandConfig / design.md where the repo has one).
3. Edit the code → reload → screenshot (the **after**).
4. Report with the before/after pair as the evidence; a claim without a screenshot is
   unverified and must be labelled so.

- **Completion criterion:** the final report contains a before and an after screenshot (or an
  explicit "not visually verified" label).

## Fable 5 rules for browser work

1. **Serial browser control.** The browser is a shared, stateful surface — never let two
   subagents drive the same Chrome. Keep browser control in the orchestrator or one dedicated
   subagent; parallelise the non-browser work around it.
2. **No reasoning-echo in browser skills.** Never instruct "explain why you clicked X" — that
   is the `reasoning_extraction` refusal trap. Ask for evidence (screenshots, console output,
   network logs) instead of narrated reasoning.
3. **Keep browser skills lean.** Intent-level steps, not click-by-click scripts; prescriptive
   step lists written for older models degrade Fable 5.

## Standing guardrails (locked feedback — do not relitigate)

- One designated Google account end-to-end; never mix accounts mid-automation.
- Vercel env vars change via `vercel env` CLI, never the dashboard UI.
- 2–3 failed attempts on the same browser action → stop and surface; don't rabbit-hole.
- Never trigger native dialogs (alert/confirm/prompt) — they deadlock the extension; use
  console.log + read_console_messages instead.

---
Routing complete when the surface is named, the loop's evidence pair exists (for UI tasks),
and no guardrail was crossed.
