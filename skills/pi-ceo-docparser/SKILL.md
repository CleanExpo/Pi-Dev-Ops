---
name: pi-ceo-docparser
description: Parse PDF / DOCX / TXT into structured ParsedDoc (text + pages + tables + metadata). Pure deterministic extraction, no LLM call. Foundation for ICP-research workflows; consumed by marketing-icp-research.
owner_role: foundational primitive — no agent boundary
status: wave-2
linear: RA-1995
---

# pi-ceo-docparser

PDF / DOCX / TXT → `ParsedDoc` primitive. No LLM. Caller is responsible
for sandboxing the source path.

## Public API

```python
from app.server.pi_ceo_docparser import parse_document, ParsedDoc

doc = parse_document("/path/to/customer-interview.pdf", max_pages=200)
if doc.error:
    log.warning("docparser: %s", doc.error)
    return
text = doc.text                # body text, page-separated by \f
pages = doc.pages              # [(1, "..."), (2, "..."), ...]
tables = doc.tables            # DOCX only — list of list-of-rows
title = doc.metadata["title"]
n_pages = doc.num_pages
```

`ParsedDoc.error` populated on any failure (missing dep, unreadable
file, unknown extension). Never raises — research pipelines should
inspect `error` and skip, not crash.

## Optional dependencies (failed-soft)

| Format | Library | Status | Fix on miss |
|---|---|---|---|
| PDF | `pymupdf` (preferred — high fidelity) | optional, AGPL | `pip install pymupdf` |
| PDF | `pypdf` (fallback — BSD pure-Python) | optional | `pip install pypdf` |
| DOCX | `python-docx` | optional, MIT | `pip install python-docx` |
| TXT | stdlib | always available | — |

Module returns `error="missing_pdf_dep"` or `"missing_docx_dep"` with
a `fix` hint in metadata when neither path is available. PDF tries
PyMuPDF first, falls through to pypdf.

## When to trigger

- Margot Wave 5 research pipeline asks "extract the customer pain
  points from this PDF interview transcript".
- marketing-icp-research consumes a customer-discovery doc.
- Any future scanner that wants to ingest a PDF/DOCX into an LLM
  context window.

## What this is NOT

- An LLM-based document QA system (use Margot's deep_research +
  File Search for that)
- An OCR pipeline — scanned PDFs without an embedded text layer
  return empty per-page text. OCR is a separate ticket if/when needed
- A general-purpose office-suite parser (no .xlsx, .pptx, .doc/legacy)

## Sequencing under autoresearch envelope

| Slot | Value |
| --- | --- |
| Single metric | parse fidelity (chars extracted vs ground-truth) |
| Time budget | 1d build + 0.5d validate |
| Constrained scope | `app/server/pi_ceo_docparser.py` |
| Strategy/tactic split | user supplies docs; module extracts text |
| Kill-switch | max_pages cap (default 500) |

## Composition with marketing-icp-research

Update `skills/marketing-icp-research/SKILL.md` to call `parse_document`
on customer-research input, then feed `doc.text` into the LLM for
JTBD / pain-point extraction. Keep parsing deterministic; delegate
classification to the LLM. Page-number citations preserved via
`doc.pages` so the model can cite "p. 3 of interview-2026-05-06.pdf".
