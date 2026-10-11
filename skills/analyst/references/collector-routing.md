> Moved from SKILL.md. Read when tasking collector skills and choosing which collector fits a question type.

## Collection layer routing

When tasking collectors, dispatch via `growth-sustainability-data` skill routing table. Analyst
owns FRAME → TASK → EVALUATE → SYNTHESISE; collectors own raw acquisition only.

| Question type | Primary collectors |
|---|---|
| Growth / channel / CAC | `cmo-growth`, `marketing-analytics-attribution`, `marketing-seo-researcher` |
| Financial sustainability | `cfo`, `analyzing-customer-patterns` |
| Technical sustainability | `cto`, `pi-seo-health-monitor`, `leverage-audit` |
| Customer retention | `cs-tier1` |
| External / market intel | `margot-bridge`, `wiki-query`, Scout (`app/server/agents/scout.py`) |
| Portfolio brand research | `marketing-icp-research`, `marketing-positioning` |
| Compounding context | `wiki-ingest` (write-back after synthesis) |
