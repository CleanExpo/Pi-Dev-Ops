# Evidence Case and Independent Review Schema

## Case example (illustrative placeholders; not a verified claim)
```json
{
  "case_id": "RESTORATION-SCOPE-0001",
  "jurisdiction": "AU-QLD",
  "artifact": { "path": "drafts/report.md", "sha256": "<actual 64-char SHA-256>" },
  "sources": [{
    "id": "S-001", "title": "Exact source title", "publisher": "Publisher institution",
    "source_type": "primary", "independence_group": "underlying-original-study-001",
    "original_url": "https://official.example/record", "edition": "2026-01",
    "retrieved_at": "2026-10-28T00:00:00+00:00",
    "path": "evidence/source-001.txt", "sha256": "<actual SHA-256 of UTF-8 extract>",
    "origin": {"status": "attested", "method": "independent official-site/manual origin check",
      "checked_by": "named-verification-service", "checked_at": "2026-10-28T00:00:00+00:00",
      "proof": {"path": "evidence/proof-001.txt", "sha256": "<actual proof SHA-256>"}}
  }],
  "claims": [{
    "id": "C-001", "text": "A material, atomic fact asserted in the finished report",
    "risk": "high", "type": "summary", "context": "Site condition and date, applicable standard and jurisdiction",
    "known_conflict": false,
    "citations": [{"source_id": "S-001", "support": "direct", "locator": "page 2, paragraph 4",
      "exact_quote": "An exact and substantive passage that appears in the source text snapshot."}]
  }]
}
```

**Note:** example contains only one source; it must HOLD until enough independent sources and legitimate reviews exist. Path values are relative to the `--root` project directory; do not expose private records in prompts to external services unless authorised.

## Observation claims
Include:
```json
"measurement": {"raw_record_source_id":"S-RAW-001","measured_at":"2026-10-28T10:00:00+10:00","instrument":"instrument identifier","unit":"% WME", "calibration_status":"documented status"}
```
The v1 gate checks required fields and that `raw_record_source_id` exists; a reviewer must inspect actual reading and calibration evidence. Do not populate estimated readings as observations.

## Calculation claims
```json
"calculation": {"operation":"multiply", "inputs":[14,4,40], "result":2240,
  "unit":"AUD ex GST", "method":"14 units × 4 days × $40 per unit per day", "tolerance":"0.01"}
```
Supported operations: `sum`, `subtract` (2 inputs), `multiply`, `divide` (2 inputs). The gate verifies arithmetic only. Domain meaning, exclusions, correct input provenance, taxes and units require independent review.

## Review file (one per independent agent)
```json
{
  "case_id":"RESTORATION-SCOPE-0001", "case_sha256":"<sha256 of canonical case JSON>",
  "reviewer":"Claude", "run_id":"unique trusted run", "model_id":"real model identifier",
  "independent_context":true, "reviewed_at":"2026-10-28T00:00:00+00:00",
  "claims":[{"id":"C-001", "verdict":"supported", "authority":"pass",
    "authentication":"pass", "accuracy":"pass", "realism":"pass", "currency":"pass",
    "contradictions":"none", "reason":"Independent evidence assessment explaining sources and limits."}],
  "signature":"<attached by trusted isolated signer, never invented by the LLM>"
}
```
For JEV, reviewer must be `JEV`, with different `run_id` and `model_id`. Accepted `verdict` for PASS: `supported`. Any `contradicted` / `unsupported` => BLOCK. Do not use non-pass dimension values to signal a PASS. `signature` must be HMAC-SHA256 over canonical JSON excluding `signature`.

## Authentication caveat
`origin.status: attested` means an independent reviewer or trusted source connector supplied an origin-verification worksheet and its checksum. It **does not** mean the gate itself cryptographically validated a publisher's identity. A version-2 trusted fetcher should produce verifiable attestations with pinned provenance.
