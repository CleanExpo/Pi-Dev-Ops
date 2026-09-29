# Output Format

Emit the review in this exact shape.

```
BRAND GUARDIAN REVIEW
Business: [DR | NRPG | RestoreAssist | CARSI | CCW | Synthex | Unite-Group]
Content type: [blog | email | social | proposal | report | landing page]
Date: [YYYY-MM-DD]
Reviewed by: Brand Guardian Agent

VERDICT: APPROVED ✅ / REVISE ❌

--- LINE-BY-LINE FEEDBACK ---

Line [N]: "[quoted text]"
Issue: [Brand voice | Factual accuracy | AI-slop | $2B filter | Client-facing]
Severity: [BLOCK | FLAG]
Fix: [Specific rewrite or action required]

Line [N]: "[quoted text]"
Issue: ...
Severity: ...
Fix: ...

--- SUMMARY ---
Blocks: [count] | Flags: [count]

REQUIRED ACTIONS BEFORE APPROVAL:
1. [Specific rewrite]
2. [Specific rewrite]

BLOCK REASON (if REVISE):
[One sentence. Posted to Linear ticket or returned to the originating agent.]
```
