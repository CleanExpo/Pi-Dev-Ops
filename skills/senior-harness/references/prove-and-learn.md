# 6. Prove and learn

Moved verbatim from SKILL.md.

## 6. Prove and learn

Validate the frozen candidate contract before execution and query admitted delivery work:

```bash
bash ~/.codex/skills/senior-harness/scripts/run_setup_driver.sh contract lint CONTRACT.json
bash ~/.codex/skills/senior-harness/scripts/run_setup_driver.sh contract ready CONTRACT.json
```

Treat exit `2` or invalid JSON as a hard stop. `lint` proves contract structure only; identity strings,
receipt labels, and its own tests are not independent proof. Schema v1 accepts candidate Capability
Packs only. Provisional or durable promotion must fail until a trusted adapter verifies signed Unlazy
receipts bound to the contract, base SHA, exact candidate SHA, command result, and independent
principal. Durable promotion additionally requires a qualified replay in a fresh workspace without
cache reuse. Bound vendor, model, runtime, or dependency changes mark the pack stale until revalidated.

The downstream driver may return only `passed`, `blocked`, `partial`, or `cancelled`. `passed` requires
contract digest, exact candidate identity, authenticated independent receipts, zero
pending/failed/abandoned/runner-error gates, and honest known-or-unknown usage.

**Complete when:** terminal status matches the receipts, promotion state matches replay evidence, and
no self-report or model grade is treated as proof.
