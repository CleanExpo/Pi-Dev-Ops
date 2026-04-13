# 01 — The Algorithm

The Ship Chain is five steps. Every Pi-CEO build runs exactly this sequence.

```
brief  →  classify  →  build_spec  →  generate  →  evaluate  →  decide  →  ship
                                           ↑_______ retry ________↓
```

---

## The five functions

### 1. `classify(brief) → intent`

Keyword match → one of five PITER categories.

```python
from app.server.core import classify

classify("fix the login crash on mobile")    # → "bug"
classify("add a dark-mode toggle")           # → "feature"
classify("upgrade all npm deps")             # → "chore"
classify("research redis vs memcached")      # → "spike"
classify("production is down right now")     # → "hotfix"
```

Source: `app/server/brief.py::classify_intent()`  
Keywords: `app/server/brief.py::_INTENT_KEYWORDS`

---

### 2. `build_spec(brief, intent, repo_url) → spec_str`

Wraps the raw brief with:
- ADW workflow steps for the intent (e.g. REPRODUCE → DIAGNOSE → FIX → VERIFY → COMMIT)
- Relevant skill context loaded from `skills/`
- Lessons from recent builds (`.harness/lessons.jsonl`)
- Strategic intent files (`.harness/intent/*.md`) when workspace is provided
- A Quality Gate the generator must pass before committing

```python
from app.server.core import build_spec

spec = build_spec("fix login crash", "bug", "https://github.com/org/repo")
# Returns a ~1200-token string ready for `claude -p`
```

Source: `app/server/brief.py::build_structured_brief()`

---

### 3. `generate(spec, workspace, model) → bool`

Runs `claude -p <spec>` in the cloned workspace. Claude reads the repo,
edits files, and commits the result.

```python
from app.server.core import generate

success = generate(spec, workspace="/tmp/my-repo", model="sonnet")
```

Source: `app/server/core/_chain.py::generate()`  
Production path: `app/server/sessions.py::_phase_generate()` (uses Agent SDK)

---

### 4. `evaluate(workspace, brief, threshold) → (score, text)`

A second `claude -p` pass reads the git diff from the last commit and scores
it on four dimensions (Completeness / Correctness / Conciseness / Format).
Returns a float 0-10 and the full evaluator text.

```python
from app.server.core import evaluate

score, text = evaluate(workspace="/tmp/my-repo", brief="fix login crash", threshold=8.0)
# score = 8.7
# text  = "COMPLETENESS: 9/10 — ...\nOVERALL: 8.7/10 — PASS"
```

Source: `app/server/core/_chain.py::evaluate()`  
Production path: `app/server/sessions.py::_run_single_eval()` (SDK, parallel Sonnet+Haiku)

---

### 5. `decide(score, threshold, attempt, max_retries) → 'pass'|'retry'|'warn'`

Three outcomes:

| Condition | Outcome |
|-----------|---------|
| `score ≥ threshold` | `"pass"` — ship it |
| `score < threshold` and retries remain | `"retry"` — inject evaluator feedback into spec, regenerate |
| `score < threshold` and no retries left | `"warn"` — ship with warning, log lesson |

```python
from app.server.core import decide

decide(8.7, threshold=8.0, attempt=0, max_retries=2)  # → "pass"
decide(6.2, threshold=8.0, attempt=0, max_retries=2)  # → "retry"
decide(6.2, threshold=8.0, attempt=2, max_retries=2)  # → "warn"
```

Source: `app/server/core/_chain.py::decide()`

---

## The complete loop in 30 lines

See `scripts/pi_essentials.py::run_ship_chain()` for the production-equivalent
loop that wires all five functions together. It is the canonical reference
implementation — if you understand that function, you understand Pi-CEO.

---

## Next

[02 — Intent Classification](02-intent-classification.md): how PITER categories
map to ADW workflow templates and why the order of keyword checking matters.
