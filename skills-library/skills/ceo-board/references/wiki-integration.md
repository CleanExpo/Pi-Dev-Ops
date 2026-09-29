# Wiki & Supabase Integration

The deliberation touches the 2nd Brain wiki and Supabase at three points: grounding (Stage 1.4,
before research), write-back (Stage 7, after the memo), and board-mandate creation (post-MEMO).
`SKILL.md` holds the trigger/skip conditions for each; this file holds the mechanics.

## Stage 1.4 — Wiki Grounding (before any external research)

Before any external research, ground the deliberation in the 2nd Brain.

1. Query Supabase wiki_pages (project: lksfwktwtmyznckodsau) for the relevant context:
   - Always read 'exit-thesis' — the $2B filter frames every board decision
   - Read the relevant business wiki page if the brief concerns a specific business
   - Read 'operational-priorities-q2-2026' for current quarter context

2. Produce a Wiki Brief under heading: `## WIKI GROUNDING (Stage 1.4)`
   Format: 3-5 bullet points of directly relevant wiki facts. Cite the page id.
   Example: "From exit-thesis: minimum ARR for $2B exit is $167M (current: $33k — gap: $166.97M)"

3. The Board MUST cite wiki facts in their deliberation when relevant.
   Personas should distinguish between "wiki-confirmed" vs "research-based" vs "my prior" claims.

**Skip Stage 1.4 only if:** brief is tagged [no-wiki] or [pure-technical] with zero strategic implications.

## Stage 7 — Wiki Write-Back (after Stage 6)

After the CEO Memo is delivered, append the decision to the relevant business wiki page.

1. Identify which business wiki page is affected (from the brief topic)
2. Read the wiki page: ~/2nd Brain/2nd Brain/Wiki/[business-slug].md
3. Append to the END of the file:

```
## Board Directives Log

### [DATE] — [TOPIC (first 60 chars)]
**Decision:** [one sentence from THE MEMO DECISION section]
**Directive to:** [from NEXT ACTIONS section — who owns the first action]
**Condition for revisit:** [first "WHAT WOULD CHANGE THIS DECISION" item]
```

4. Run the wiki sync: python3 ~/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py

5. Insert into Supabase board_directives table:
   ```sql
   INSERT INTO board_directives (business_slug, date, topic, decision, directive_to, status)
   VALUES ('[slug]', '[date]', '[topic]', '[decision]', '[directive_to]', 'active')
   ```
   Use the Supabase MCP tool if available, or skip if not in scope.

**Skip Stage 7 if:** brief is tagged [no-wiki-write] or the board could not reach a conclusion.

## Post-MEMO — Create Board Mandate

After the MEMO is delivered, if NEXT ACTIONS contain agent-executable items:

```python
import json, urllib.request, ssl, os, re

SUPABASE_URL = "https://lksfwktwtmyznckodsau.supabase.co"
env = open(os.path.expanduser("~/.hermes/.env")).read()
# Get service key from Vercel env or Supabase directly

for action in next_actions:
    if action.get('owner') in ['me', 'Engineering', 'PM-Core', 'Agent']:
        mandate = {
            "title": action['title'],
            "scope": action['description'],
            "project_id": action.get('project', 'unite-group'),
            "team": action.get('team', 'Unite-Group'),
            "authority": "sandbox",
            "status": "active",
            "board_memo": full_memo_text,
        }
        # POST to Supabase board_mandates
```

Notify Phill: "Board mandate created for [N] actions. PM-Core will begin in the next scheduled window. Hourly audio briefings will track progress."
