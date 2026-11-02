---
name: living-business-os
description: Run the Living Business OS rules (the Unite Group draft-only decision contracts) through the verified lbos command line, on synthetic data only. Use when a verifier or builder must check an LBOS input, rank improvement proposals, list the owner questions, or confirm the package identity before a consumer relies on it. It never publishes, never touches real customer data, and every result needs human approval.
---

# living-business-os

One owner for the Living Business OS contracts and decision code: `packages/living-business-os/` (`@unite-group/living-business-os`). This file says how to call it. It holds no rule text; the rules are the package source, and the package states and proves its own identity.

## When to use

- A verifier needs to confirm an LBOS input is valid, or that a consumer's copy is the pinned package.
- A builder needs the ranked, draft-only proposals (`decide`) or the owner questions (`questions`) for a synthetic business.
- Someone asks "is this the real package?" Run `version` and read `identity`.

Do not use it for real customer data. Real-data use needs its own admission (SYN-1373). The verifier role keeps its risk ceiling at 0; this skill grants no runtime authority.

## Caller

```bash
node packages/living-business-os/bin/lbos.mjs <command> [<contract>] [--input <path>]
```

With no `--input`, JSON is read from stdin. Use Node 22.x.

| Command | Input | Result |
|---|---|---|
| `version` | none | `{ "origin_sha": "<Synthex commit the rules were taken from>" }` |
| `validate <contract>` | one object; contract is `business-intent`, `opportunity-signal`, `fulfilment-request` or `customer-interaction` | the parsed value (defaults applied, strings trimmed) |
| `decide` | `{ "intent": {...}, "signals": [...] }` | ranked proposals; draft only, approval required |
| `questions` | `{ "intent", "signals", "answeredQuestionIds": [...] }` (the field is required; the array may be empty; ids unique, at most 100) | at most 3 owner questions |
| `idempotency-key` | one fulfilment request | `{ "key": "..." }` |

Example, with a synthetic business:

```bash
echo '{"intent": {"organizationId":"org-demo-1","businessName":"Demo Cafe","goals":["More weekday bookings"],"serviceIds":["svc-catering"],"capacity":{"availableJobsPerWeek":10,"bookedJobsPerWeek":6,"updatedAt":"2026-11-01T00:00:00+10:00"},"constraints":{"maximumMonthlyAutomationCostAud":50,"publishing":"approval_required","customerDataReuse":"tenant_only"}}, "signals": [], "answeredQuestionIds": []}' \
  | node packages/living-business-os/bin/lbos.mjs questions
```

## Output

stdout is always exactly one JSON object followed by a newline:

```json
{
  "ok": true,
  "command": "decide",
  "identity": "verified",
  "contract_version": "lbos.contracts.v1",
  "package_version": "1.0.0",
  "package_digest": "<sha256>",
  "draft_only": true,
  "approval_required": true,
  "result": "...",
  "error": null
}
```

On failure `ok` is false, `result` is null and `error` is `{ "code", "message", "issues": [{ "path", "code" }] }`. Messages are fixed text per code. Issues carry codes and paths only: no zod message, no input value, no unknown key name.

If the identity check fails, `identity` is `"unverified"` and the version, contract version and digest are `null`. Never read a version off an unverified envelope.

## Exit codes

| Exit | Code | Meaning |
|---|---|---|
| 0 | none | success (`research_more` and `defer_for_capacity` are successes) |
| 2 | `INVALID_INPUT` | schema failure, malformed or empty JSON, wrong top-level type, duplicate answered ids, evidence from another tenant |
| 3 | `USAGE` | unknown command or contract, bad or unreadable `--input`, extra arguments |
| 4 | `INTEGRITY`, `DEPENDENCY_MISSING` | the package is not the pinned one, or zod could not load. Reinstall from the pinned SHA. The runner never runs a partial copy |
| 5 | `INPUT_TOO_LARGE` | over 262,144 bytes, over 500 signals, or input not complete within 5 seconds |
| 6 | `TENANT_MISMATCH`, `UNKNOWN_SERVICE`, `CONFLICTING_SIGNAL_ID` | the engine's own domain refusals |
| 70 | `INTERNAL` | anything else; report it, keep the input locally |

## Forbidden

- Real customer or tenant data. Synthetic fixtures only. On success the command returns the input fields it was given (`validate` returns the parsed value, `decide` returns titles and metrics), so the echo of a real value would land in your logs. Redaction applies to failure envelopes only.
- Treating a result as a decision. Every proposal is draft only and `approvalStatus` is always `required`.
- Editing `packages/living-business-os/src/*.ts`, `dist/`, `MANIFEST.json` or the goldens by hand. Rule changes go through the package's compatibility rule (major, minor, patch) and its goldens.
- Using it to publish, send, bill or write anywhere. It writes nothing.
- Relying on consent or authorisation receipt strings as proof. The package treats them as references it does not verify; the consumer owns authentication, receipt lookup, current consent and withdrawal.

## Not provided

A Python port, a JSON Schema export, a dashboard, the contract 5 measure-and-learn loop, and any caller that runs `decide` on real data.

## Proof

`cd packages/living-business-os && npm run conformance` asserts the environment (Node 22.22.3, C locale, UTC), verifies the file inventory, rebuilds `dist/` outside the package and compares it file for file, and checks every golden byte for byte against the outputs captured from Synthex `5445287f7`.
