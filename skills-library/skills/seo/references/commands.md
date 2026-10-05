# How To Run Each Command

All scripts live at `~/.claude/skills/seo/scripts/` and have shebangs pinned to the
skill's isolated venv. Call them directly — no `python3` prefix. The command index is the
Quick Reference table in `SKILL.md`; this file holds the exact invocation + output spec for each.

## `/seo quick <domain>`

A 60-second snapshot. Run these three calls in parallel and synthesize:

```bash
~/.claude/skills/seo/scripts/domain_overview.py overview --target <domain>
~/.claude/skills/seo/scripts/backlinks.py summary --target <domain>
~/.claude/skills/seo/scripts/domain_overview.py ranked --target <domain> --limit 25
```

Produce a 5-line summary: estimated organic traffic, total keywords ranking,
backlink count, top 5 keywords by volume, and one headline opportunity.

## `/seo audit <domain>` — Full Audit (Parallel Subagents)

Delegate to the five specialist subagents **in parallel** using the Agent tool:

| Subagent | What it produces |
|----------|------------------|
| `seo-keywords` | Keyword Score + top opportunities |
| `seo-technical` | Technical Score + crawl issues |
| `seo-competitors` | Competitive Score + top 10 competitors + SERP overlap |
| `seo-content` | Content Score + content gap topics |
| `seo-backlinks` | Authority Score + backlink profile + toxicity flags |

Each subagent calls the appropriate scripts, summarizes findings, and returns
a structured block. Then:

1. Compute the **composite SEO Score** as a weighted average:
   `overall = 0.25*keywords + 0.25*technical + 0.20*competitors + 0.15*content + 0.15*authority`
2. Build an audit JSON object matching `schema/audit_input.example.json`.
3. Write it to `~/.claude/skills/seo/output/<domain>-audit.json`.
4. Offer to generate the PDF: `/seo report-pdf <domain>`.

## `/seo keywords <seed>`

```bash
~/.claude/skills/seo/scripts/keyword_research.py related "<seed>" --limit 200
~/.claude/skills/seo/scripts/keyword_research.py suggestions "<seed>" --limit 100
```

Group results by intent (informational, commercial, transactional, navigational).
Surface the **20 best opportunities** ranked by `volume / (difficulty + 1)`.
Always include CPC so the user sees commercial value.

## `/seo technical <domain>`

```bash
~/.claude/skills/seo/scripts/on_page_audit.py site --target <domain> --max-crawl-pages 100
```

This kicks off a real crawl and waits for results (can take 2-5 minutes for
100 pages). When complete, group issues by severity (critical, high, medium,
low) and produce a prioritized fix list. Always include estimated impact.

For a quick single-page audit:

```bash
~/.claude/skills/seo/scripts/on_page_audit.py page --url <url>
```

## `/seo competitors <domain>`

```bash
~/.claude/skills/seo/scripts/domain_overview.py competitors --target <domain> --limit 20
```

For the top 5 competitors, also pull their ranked keywords and intersect with
the user's domain to identify SERP overlap and content gaps. Output:

- Top 10 competitors table (domain, organic keywords, traffic estimate)
- Shared keywords vs. unique keywords for each competitor
- 3 specific competitors to study most closely (and why)

## `/seo content <domain>`

```bash
~/.claude/skills/seo/scripts/domain_overview.py ranked --target <domain> --limit 200
```

Cluster the ranked keywords into topics. Identify:
- Strong topics (5+ keywords ranking top 10)
- Weak topics (lots of keywords, none top 10 — opportunity)
- Missing topics (competitors have them, you don't — use content_gap)

## `/seo backlinks <domain>`

```bash
~/.claude/skills/seo/scripts/backlinks.py summary --target <domain>
~/.claude/skills/seo/scripts/backlinks.py refdomains --target <domain> --limit 50
~/.claude/skills/seo/scripts/backlinks.py anchors --target <domain> --limit 30
```

Report on: total backlinks, referring domains, dofollow ratio, top anchors
(flag over-optimization), top referring domains by rank, and any toxicity
indicators (spam score, suspicious patterns).

## `/seo rankings <domain> <keyword1> <keyword2> ...`

```bash
~/.claude/skills/seo/scripts/serp_check.py rank --domain <domain> --keywords kw1 kw2 ...
```

Returns position (or "not in top 100") for each keyword. Group by:
- 🟢 Position 1-3 (winning)
- 🟡 Position 4-10 (page 1 — fight for top 3)
- 🟠 Position 11-30 (close — push to page 1)
- 🔴 Position 31-100 / not ranking (long-haul or pivot)

## `/seo content-gap <you> <competitor>`

```bash
~/.claude/skills/seo/scripts/domain_overview.py content_gap --you <you> --competitors <comp>
```

Returns keywords the competitor ranks for and you don't. Sort by search
volume × ranking position (closer to page 1 = easier wins for them).

## `/seo compare <domain1> <domain2>`

Run `overview`, `ranked` (limit 50), and `summary` for **both** domains in
parallel, plus an `intersect` call to find shared keywords. Output a
side-by-side comparison table covering keywords, traffic, backlinks,
referring domains, top shared keywords, and a verdict.

## `/seo report-pdf <domain>`

```bash
~/.claude/skills/seo/scripts/generate_pdf_report.py \
    --input ~/.claude/skills/seo/output/<domain>-audit.json \
    --output ~/.claude/skills/seo/output/<domain>-report.pdf
```

Requires that `/seo audit` ran first and saved the JSON. Open the PDF when done.
