---
name: pii-redactor
description: Detect and redact personally identifiable information from any payload before it enters logs, prompts, or outbound messages. ≥95% precision, ≤5% false-positive rate. Non-negotiable in front of every Scribe send and every email-listener intake. Closes Hermes Sprint 1 SWARM-005 requirement.
owner_role: Scribe (binds in front of every send)
status: wave-2
---

# pii-redactor

Two-pass PII detection: regex (cheap, high-recall) + Claude classification (slow, high-precision). Redacts in place; preserves structure.

## Why this exists

Per the Hermes-Swarm Recommendation §5: PII filter is non-negotiable across every send. `email-listener` ingests the highest-PII surface in the system. `telegram-draft-for-review` may surface user-private corpus content in research summaries. Both need a redaction layer in front.

The Wave 1 Scribe skill notes "PII redactor (Wave 2) MUST run between research and draft." This skill is that layer.

## Detection categories

| Category | Pattern | Replacement |
|---|---|---|
| Credit card | Luhn-validated 13-19 digit sequences | `[CARD-REDACTED]` |
| US SSN | `\d{3}-\d{2}-\d{4}` | `[SSN-REDACTED]` |
| UK NI number | `^[A-Z]{2}\d{6}[A-Z]$` | `[NI-REDACTED]` |
| Australian TFN | 8-9 digit sequences with checksum | `[TFN-REDACTED]` |
| Email address | RFC-5322 + ICANN TLD validation | `[EMAIL-REDACTED]` |
| Phone (intl) | E.164 with country code | `[PHONE-REDACTED]` |
| API key (OpenAI, Anthropic, GitHub, AWS) | Provider-specific prefixes (`sk-`, `claude-api-`, `ghp_`, `AKIA`) | `[KEY-REDACTED]` |
| Bearer tokens | `Bearer [A-Za-z0-9._-]{20,}` | `Bearer [TOKEN-REDACTED]` |
| Password fields | `(password|passwd|pwd)\s*[:=]\s*\S+` | `password=[REDACTED]` |
| Postcode (UK / AU / US ZIP) | format-validated | preserved (low risk, useful context) |
| Names of attendees / contacts | Claude classify | `[NAME-REDACTED-{role}]` only when context flags privacy-sensitive |

## Pipeline

```
input_payload → regex_pass → flagged_regions
                          ↓
              if any high-confidence regex match → redact in place
                          ↓
              claude_classify(remaining_text, "Are there any PII strings the regex missed?")
                          ↓
              merge classifier hits → final redacted payload
                          ↓
              emit: { redacted: <payload>, redaction_log: [<hits>], precision_score: 0.0-1.0 }
```

## Contract

**Input:**
```json
{
  "payload": "<text or JSON>",
  "context": "telegram_send" | "log_emit" | "research_intake" | "email_intake",
  "preserve_structure": true,
  "strictness": "standard" | "high"
}
```

**Output:**
```json
{
  "redacted_payload": "...",
  "redaction_count": 0,
  "redaction_log": [
    { "category": "EMAIL", "original_offset": 142, "length": 24, "method": "regex" }
  ],
  "precision_score": 0.97,
  "passed": true
}
```

**Failure mode:** if precision_score < 0.95, skill returns `passed: false` and refuses to release the redacted payload. Caller must fall back to Telegram-asking-the-user or abort.

## Safety bindings

- **Never log the original payload** in an unredacted form. Only `redaction_log` (offsets + categories) lands in `.harness/swarm.jsonl`.
- **Never round-trip the original through Claude.** Classifier sees a salted hash of the original alongside the text under test, NOT the raw text in audit form.
- **Strictness levels.** `standard` = redact obvious PII; `high` = also redact names, attendee lists, location strings. Default `standard` for Telegram drafts; `high` for email intake.
- **Whitelist for known-public strings.** A small allowlist of public addresses / contacts (`info@unite-group.com.au`, public Telegram bot username) bypasses redaction. Allowlist file: `Pi-Dev-Ops/.harness/pii_allowlist.json`. Edits require user approval (audit-trailed).
- **No regex bypass via encoding.** Pre-process payloads through Unicode normalization + base64-decode-if-detected to catch `c%72edit%20card%201234...` style attempts.

## Where the redactor sits

Two integration points in Wave 2:

1. **`email-listener`** → after fetching email body, BEFORE composing intent payload. Always strictness=high.
2. **`telegram-draft-for-review`** → before posting the draft to review chat AND before the final send. Always strictness=standard for review chat (user needs context to approve), but redacts again to strictness=high before the actual send if the review chat differs from the destination.

## Verification

Test corpus: `Pi-Dev-Ops/.harness/pii_test_corpus.jsonl` (build in Wave 2):
- 100 known-PII samples (credit cards, SSNs, emails, API keys mixed in prose)
- 100 known-clean samples (general business email body)
- 50 ambiguous samples (postcodes, partial names, common words that look like keys)

Targets:
- ≥95% precision on PII samples (≥95 of 100 PII strings detected)
- ≤5% false-positive rate on clean samples (≤5 of 100 non-PII strings flagged)
- ≤10% over-redaction on ambiguous samples (over-cautious is OK, just not punishing context loss)

Re-run on every change to the pattern set. CI gate.

## When NOT to use

- For payloads going to local-only logs that the user reads (not exposed externally) — over-redaction reduces signal. Use strictness=`standard` instead.
- For research intake from Margot when the corpus IS the user's private notes — those are already inside the trust boundary; redacting them defeats the corpus. (Caller decides.)
- For test fixtures — explicitly excluded.

## Out of scope for Wave 2

- Image PII (faces, license plates) — requires separate model, Wave 3 candidate.
- PDF / DOCX redaction — Wave 3 with attachment processing.
- Healthcare-specific PII (HIPAA) — out of jurisdiction; not a Pi-CEO concern.
- Multilingual PII detection — Wave 3 if Phill expands non-English use.

## References

- Hermes Sprint 1 SWARM-005 requirement: `/Users/phill-mac/Pi-CEO/Hermes-Swarm-Recommendation-2026-04-14.md` §7
- 15 mandatory safety controls §5 (same memo)
- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
