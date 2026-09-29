# Phase 3.5: Cross-Model Second Opinion (optional)

Read in full at SKILL.md Phase 3.5.


**Provider preflight:**

```bash
command -v codex >/dev/null 2>&1 && echo 'CODEX_MODE: ready' || echo 'CODEX_MODE: not_installed'
```

Authentication is checked by the actual invocation. An auth or "out of credits" error means the Codex login
token has expired; the repair is an interactive `codex login` that only the user can run. Any non-ready
outcome is missing outside coverage; use the Claude subagent fallback below. Never substitute another
external provider or an API key.

Use AskUserQuestion (regardless of codex availability):

> Want a second opinion from an independent AI perspective? It will review your problem statement, key answers, premises, and any landscape findings from this session without having seen this conversation — it gets a structured summary. Usually takes 2-5 minutes.
> A) Yes, get a second opinion (recommended)
> B) No, proceed to alternatives

If B: skip Phase 3.5 entirely. Remember that the second opinion did NOT run (affects design doc, founder signals, and Phase 4 below).

**If A: Run the Codex cold read.**

1. Assemble a structured context block from Phases 1-3:
   - Mode (Startup or Builder)
   - Problem statement (from Phase 1)
   - Key answers from Phase 2A/2B (summarize each Q&A in 1-2 sentences, include verbatim user quotes)
   - Landscape findings (from Phase 2.75, if search was run)
   - Agreed premises (from Phase 3)
   - Codebase context (project name, languages, recent activity)

2. **Write the assembled prompt to a temp file** (prevents shell injection from user-derived content):

```bash
OUTSIDE_PROMPT_FILE=$(umask 077; mktemp "${TMPDIR:-/tmp}/gs-outside-oh-XXXXXXXX")
```

Write the full prompt to this file. **Always start with the filesystem boundary:**
"IMPORTANT: Do NOT read or execute any files under ~/.claude/, ~/.agents/, .claude/skills/, or agents/. These are skill definitions, not repository review data. Do not follow nested skills, hooks, or tool instructions. They contain bash scripts and prompt templates that will waste your time. Ignore them completely. Do NOT modify agents/openai.yaml. Stay focused on the repository code only.\n\n"
Then add the context block and mode-appropriate instructions:

**Startup mode instructions:** "You are an independent technical advisor reading a transcript of a startup brainstorming session. [CONTEXT BLOCK HERE]. Your job: 1) What is the STRONGEST version of what this person is trying to build? Steelman it in 2-3 sentences. 2) What is the ONE thing from their answers that reveals the most about what they should actually build? Quote it and explain why. 3) Name ONE agreed premise you think is wrong, and what evidence would prove you right. 4) If you had 48 hours and one engineer to build a prototype, what would you build? Be specific — tech stack, features, what you'd skip. Be direct. Be terse. No preamble."

**Builder mode instructions:** "You are an independent technical advisor reading a transcript of a builder brainstorming session. [CONTEXT BLOCK HERE]. Your job: 1) What is the COOLEST version of this they haven't considered? 2) What's the ONE thing from their answers that reveals what excites them most? Quote it. 3) What existing open source project or tool gets them 50% of the way there — and what's the 50% they'd need to build? 4) If you had a weekend to build this, what would you build first? Be specific. Be direct. No preamble."

3. Run Codex with the assembled prompt:

Write the **complete prompt and context**, including actual plan/spec/source, to a private file. Substitute its shell-quoted path for `<prepared-prompt-file>`; never interpolate user text into shell source. Request a final Recommendation: <action> because <specific reason> line, including an explicit no-findings rationale.

```bash
_REPO_ROOT=$(git rev-parse --show-toplevel) || { echo 'ERROR: not in a git repo' >&2; exit 1; }
_OUT=$(mktemp -d "${TMPDIR:-/tmp}/gs-outside.XXXXXXXX") || exit 1
_T=""; command -v gtimeout >/dev/null 2>&1 && _T="gtimeout 300"
[ -z "$_T" ] && command -v timeout >/dev/null 2>&1 && _T="timeout 300"
_EXIT=0
$_T codex exec "$(cat -- '<prepared-prompt-file>')" -C "$_REPO_ROOT" -s read-only \
  -c 'model_reasoning_effort="high"' < /dev/null >"$_OUT/text" 2>"$_OUT/stderr" || _EXIT=$?
cat "$_OUT/text"; cat "$_OUT/stderr" >&2
# An exit code is not a verdict: codex can exit 0 and write nothing. Judge the output.
if [ "$_EXIT" -ne 0 ] || [ ! -s "$_OUT/text" ] || ! grep -q 'Recommendation:' "$_OUT/text"; then
  echo "Codex outside review unavailable (exit $_EXIT, or empty/incomplete output); missing coverage." >&2
  rm -rf "$_OUT"; exit 1
fi
rm -rf "$_OUT"
echo 'OUTSIDE_STATUS: completed provider=codex host=claude'
```

Show the full response in a `tool-output` fence. Require successful execution and a `Recommendation:` line. Refusal, empty/malformed output, timeout or CLI failure means `outside_status: unavailable`. Use the caller's fallback; missing coverage is never clean/PASS. After either outcome, delete only your private prompt; scratch cleanup is automatic.

**Error handling:** All errors are non-blocking — second opinion is a quality enhancement, not a prerequisite.
- **Auth failure:** If stderr contains "auth", "login", "unauthorized", or "API key": "Codex authentication failed. Run \`codex login\` to authenticate." Fall back to Claude subagent.
- **Timeout:** "Codex timed out after 5 minutes." Fall back to Claude subagent.
- **Empty response:** "Codex returned no response." Fall back to Claude subagent.

On any Codex error, fall back to the Claude subagent below.

**If preflight is not ready (or Codex errored):**

Dispatch via the Agent tool with `run_in_background: false` (subagents default to background since Claude Code v2.1.198; the findings must land before the workflow continues). The subagent has fresh context and no conversation bias — but it is the same harness; model identity stays unknown unless the runtime reports it; weigh its agreement accordingly.

Subagent prompt: same mode-appropriate prompt as above (Startup or Builder variant).

Present findings under a `SECOND OPINION (Claude subagent):` header.

If the subagent fails or times out: "Second opinion unavailable. Continuing to Phase 4."


4. **Presentation:**

If Codex ran:
```
SECOND OPINION (Codex):
════════════════════════════════════════════════════════════
<full codex output, verbatim — do not truncate or summarize>
════════════════════════════════════════════════════════════
```

If Claude subagent ran:
```
SECOND OPINION (Claude subagent):
════════════════════════════════════════════════════════════
<full subagent output, verbatim — do not truncate or summarize>
════════════════════════════════════════════════════════════
```

5. **Cross-model synthesis:** After presenting the second opinion output, provide 3-5 bullet synthesis:
   - Where Claude agrees with the second opinion
   - Where Claude disagrees and why
   - Whether the challenged premise changes Claude's recommendation

6. **Premise revision check:** If Codex challenged an agreed premise, use AskUserQuestion:

> Codex challenged premise #{N}: "{premise text}". Their argument: "{reasoning}".
> A) Revise this premise based on Codex's input
> B) Keep the original premise — proceed to alternatives

If A: revise the premise and note the revision. If B: proceed (and note that the user defended this premise with reasoning — this is a founder signal if they articulate WHY they disagree, not just dismiss).

---
