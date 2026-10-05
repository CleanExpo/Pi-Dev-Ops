# Visual Sketch (UI ideas only)

Read after SKILL.md Phase 4 is answered, only when the chosen approach has user-facing UI.


If the chosen approach involves user-facing UI (screens, pages, forms, dashboards,
or interactive elements), generate a rough wireframe to help the user visualize it.
If the idea is backend-only, infrastructure, or has no UI component — skip this
section silently.

**Step 1: Gather design context**

1. Check if `DESIGN.md` exists in the repo root. If it does, read it for design
   system constraints (colors, typography, spacing, component patterns). Use these
   constraints in the wireframe.
2. Apply core design principles:
   - **Information hierarchy** — what does the user see first, second, third?
   - **Interaction states** — loading, empty, error, success, partial
   - **Edge case paranoia** — what if the name is 47 chars? Zero results? Network fails?
   - **Subtraction default** — "as little design as possible" (Rams). Every element earns its pixels.
   - **Design for trust** — every interface element builds or erodes user trust.

**Step 2: Generate wireframe HTML**

Generate a single-page HTML file with these constraints:
- **Intentionally rough aesthetic** — use system fonts, thin gray borders, no color,
  hand-drawn-style elements. This is a sketch, not a polished mockup.
- Self-contained — no external dependencies, no CDN links, inline CSS only
- Show the core interaction flow (1-3 screens/states max)
- Include realistic placeholder content (not "Lorem ipsum" — use content that
  matches the actual use case)
- Add HTML comments explaining design decisions

Create a private directory for it first — the renderer serves that whole directory
over loopback, so it must be yours alone and hold nothing else (never a fixed,
shared /tmp name another user could pre-create):
```bash
mktemp -d "${TMPDIR:-/tmp}/gs-sketch.XXXXXX"
```
Write the sketch to `<that directory>/sketch.html` (Write tool).

**Step 3: Render and capture**

Open the sketch for the user: `open <sketch-dir>/sketch.html`. If this session has a
browser screenshot tool (for example the Playwright MCP), capture
`<sketch-dir>/sketch.png` at 1280px wide and Read it; otherwise skip the screenshot
and say so. Never install a browser or renderer for the user.

**Step 4: Present and iterate**

Show the screenshot (or the opened page) to the user. Ask: "Does this feel right? Want to iterate on the layout?"

If they want changes, regenerate the HTML with their feedback and re-render.
If they approve or say "good enough," proceed.

**Step 5: Include in design doc**

Reference the wireframe screenshot in the design doc's "Recommended Approach" section.
The screenshot file at `<sketch-dir>/sketch.png` (or the HTML, if no screenshot) — name the full path in
the doc — lets later reviews see what was originally envisioned.

**Step 6: Outside design voices** (optional)

After the wireframe is approved, offer outside design perspectives:

```bash
command -v codex >/dev/null 2>&1 && echo 'CODEX_MODE: ready' || echo 'CODEX_MODE: not_installed'
```

If Codex is available, use AskUserQuestion:
> "Want outside design perspectives on the chosen approach? Codex proposes a visual thesis, content plan, and interaction ideas. A Claude subagent proposes an alternative aesthetic direction."
>
> A) Yes — get outside design voices (recommended)
> B) No — proceed without

If user chooses A, run both independent voices below and wait for both results before synthesis. They may overlap when the host supports parallel tool calls; the native subagent call remains blocking.

1. **Codex** (via Bash, `model_reasoning_effort="medium"`):
Prompt: "For this product approach, provide: a visual thesis (one sentence — mood, material, energy), a content plan (hero → support → detail → CTA), and 2 interaction ideas that change page feel. Apply beautiful defaults: composition-first, brand-first, cardless, poster not document. Be opinionated." Include the approved product approach and wireframe source in the prepared prompt.

Write the **complete prompt and context**, including actual plan/spec/source, to a private file. Substitute its shell-quoted path for `<prepared-prompt-file>`; never interpolate user text into shell source. Request a complete design proposal ending with Recommendation: <direction> because <product-specific reason>.

```bash
_REPO_ROOT=$(git rev-parse --show-toplevel) || { echo 'ERROR: not in a git repo' >&2; exit 1; }
_OUT=$(mktemp -d "${TMPDIR:-/tmp}/gs-outside.XXXXXXXX") || exit 1
_T=""; command -v gtimeout >/dev/null 2>&1 && _T="gtimeout 300"
[ -z "$_T" ] && command -v timeout >/dev/null 2>&1 && _T="timeout 300"
_EXIT=0
$_T codex exec "$(cat -- '<prepared-prompt-file>')" -C "$_REPO_ROOT" -s read-only \
  -c 'model_reasoning_effort="medium"' < /dev/null >"$_OUT/text" 2>"$_OUT/stderr" || _EXIT=$?
cat "$_OUT/text"; cat "$_OUT/stderr" >&2
# An exit code is not a verdict: codex can exit 0 and write nothing. Judge the output.
if [ "$_EXIT" -ne 0 ] || [ ! -s "$_OUT/text" ] || ! grep -q 'Recommendation:' "$_OUT/text"; then
  echo "Codex outside review unavailable (exit $_EXIT, or empty/incomplete output); missing coverage." >&2
  rm -rf "$_OUT"; exit 1
fi
rm -rf "$_OUT"
echo 'OUTSIDE_STATUS: completed provider=codex host=claude'
```

Show the full response in a `tool-output` fence. Require successful execution and a `Recommendation:` line. Refusal, empty/malformed output, timeout or CLI failure means `outside_status: unavailable`. Continue completed proposals; native completion does not count as outside coverage. After either outcome, delete only your private prompt; scratch cleanup is automatic.


2. **Claude subagent** (via Agent tool, `run_in_background: false` — subagents default to background since Claude Code v2.1.198):
"For this product approach, what design direction would you recommend? What aesthetic, typography, and interaction patterns fit? What would make this approach feel inevitable to the user? Be specific — font names, hex colors, spacing values."

Present Codex output under `CODEX SAYS (design sketch):` and subagent output under `CLAUDE SUBAGENT (design direction):`.
Error handling: all non-blocking. On failure, skip and continue.

---
