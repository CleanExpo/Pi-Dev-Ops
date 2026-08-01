# Gap enumeration request — migration harness coverage map

You are NOT reviewing a diff. You are auditing a **coverage map** for completeness.

Read: `D:\Pi-Dev-Ops\docs\HARNESS-COVERAGE-MAP-2026-08-01.md`

It lists 8 checks (C1-C8), 10 structural gaps (G1-G10), and assesses 5 named safety
constraints of a capability called operator-gateway (OG1-OG5).

## Context you need

The harness guards a port of code between two Next.js apps. The claim it checks is
deliberately bounded and diff-relative: **"this port introduces no network/DB/execution
construct the named source baseline did not already contain."** It explicitly does NOT
claim absolute read-only proof — that was tried and correctly rejected as an unbounded
negative.

The last capability to be ported, operator-gateway, is an execution surface whose entire
safety story is: no production DB writes, no external execution, no live runner, no API
keys, no real execute button.

## What I want from you

**Enumerate the classes of defect that are MISSING from this map.** Not a re-listing of
G1-G10 — what is absent from them.

For each missing class:
1. Name it and describe the concrete failure it permits.
2. Say which of C1-C8 you would expect to catch it, and why none does.
3. State whether it is bounded/decidable (buildable as a check) or requires runtime or
   architectural evidence.
4. Say whether it specifically threatens OG1-OG5.

Then answer three questions directly:

- **Q1.** Is the OG1-OG5 assessment honest, or is any "PARTIAL" actually "NO"?
- **Q2.** G10 says a port that *deletes* a safety check passes because counts only fail
  on increase. Are there other one-directional blind spots of that shape?
- **Q3.** If you could add exactly ONE check before operator-gateway is ported, which,
  and what would it catch that nothing else does?

Be adversarial. Assume the map's author is motivated to believe coverage is better than
it is. Do not soften. Under 700 words.
