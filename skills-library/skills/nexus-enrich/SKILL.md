---
name: nexus-enrich
description: "Take a list of entities (companies, people, domains, products, leads) and fill in the requested fields for each from the web, returning a table with a source per cell and a blank where nothing was found. The estate's replacement for a metered list-building or enrichment API. Use when handed a CSV, spreadsheet or list that needs columns completed."
---

# Nexus Enrich

Turn a list of entities into a table of sourced facts. The hard requirement: **a blank cell is
a valid answer and a fabricated one is a defect.**

## Contract first

Before any lookup, restate and get straight:

- **The entities** — how many, and how each is identified (legal name, domain, LinkedIn URL).
  Ambiguous identity is the main source of wrong data. `Acme Pty Ltd` and `Acme Group` are two
  entities until proven otherwise.
- **The fields** — exactly what each column means. "Size" is not a field; "employee count as
  reported on LinkedIn" is.
- **The bar** — what counts as an acceptable source for each field.

If the list is large, say what the run will cost in time and calls before starting.

## Procedure

**1. Resolve identity before enriching.** For each entity, first confirm which real-world thing
it is — usually its official domain. Enriching the wrong company is worse than a blank row.

**2. Search per entity, batched by field where possible.** `mcp__exa__web_search_exa` with
`category:company` or `category:people` for entity lookups. Routes:
`~/.claude/skills/library/web-tool-tiers.md`.

**3. Read the authoritative page, not the aggregator.** A company's own site, filing, or
pricing page beats a directory that scraped it two years ago.

**4. Record a source per cell.** Not per row. If four columns came from three pages, the table
must be able to show which cell came from where.

**5. Leave it blank when it is not found.** Never infer an email format, estimate a headcount,
or guess a price. An empty cell with "not found" is correct output.

## Output shape

A table with one row per input entity, in the input order, plus:

- A `source` column or per-cell citation.
- A `confidence` marker where identity resolution was uncertain.
- A short list of entities that could not be resolved at all, and why.
- Counts: how many rows fully populated, partially populated, blank.

Write to CSV when the list exceeds roughly 20 rows; keep it inline below that.

## Australian data notes

For Australian entities, the authoritative sources are ABN Lookup (ABN, entity name, GST
status), ASIC (company registration), and the entity's own site. Prefer these over commercial
directories, which are frequently stale.

## Do not

- Do not pattern-guess contact details. `firstname@domain` is a guess, not a finding.
- Do not carry an aggregator's stale figure without dating it.
- Do not silently drop entities that failed. Every input row appears in the output.
- Do not scrape personal data beyond the fields requested, and flag anything that looks like
  it needs a lawful basis before it is used for outreach.

## Resources

- `~/.claude/skills/library/web-tool-tiers.md` — tier order, route status, shared rules.
