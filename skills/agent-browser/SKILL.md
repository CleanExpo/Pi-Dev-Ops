---
name: agent-browser
description: Browser automation CLI for AI agents. Use when the user needs to interact with websites, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, testing web apps, or automating any browser task. Triggers include requests to "open a website", "fill out a form", "click a button", "take a screenshot", "test this web app", "login to a site", "automate browser actions", or any task requiring programmatic web interaction. Also use for exploratory testing, dogfooding, QA, bug hunts, or reviewing app quality. Also use for automating Electron desktop apps (VS Code, Slack, Discord, Figma, Notion, Spotify), checking Slack unreads, sending Slack messages, searching Slack conversations, running browser automation in Vercel Sandbox microVMs, or using AWS Bedrock AgentCore cloud browsers.
allowed-tools: Bash(agent-browser:*), Bash(npx agent-browser:*)
hidden: true
metadata:
  adapted_from: coleam00/skills (MIT, © 2026 Cole Medin) — https://github.com/coleam00/skills, accessed 17/08/2026
  adaptations: estate scope guard added; routing precedence stated
---

# agent-browser

Fast browser automation CLI for AI agents. Chrome/Chromium via CDP with accessibility-tree snapshots and compact `@eN` element refs.

Install: `npm i -g agent-browser && agent-browser install`

## Start here

This file is a discovery stub, not the usage guide. Before running any `agent-browser` command, load the actual workflow content from the CLI:

```bash
agent-browser skills get core             # start here — workflows, common patterns, troubleshooting
agent-browser skills get core --full      # include full command reference and templates
```

The CLI serves skill content that always matches the installed version, so instructions never go stale. **Keep this stub thin on purpose.** Inlining the workflow here would create a second copy that drifts from the installed CLI with nothing detecting it — the deployed-versus-template failure this repo's `deploy_skills.py` exists to prevent.

## Scope guard — read before pointing this at anything

**This skill is for authenticated or owned surfaces, and for QA and dogfooding our own products.** M365/Outlook, client portals, our own dashboards, Slack, and the products we ship.

**Do not build, add, or reach for CAPTCHA, Cloudflare Turnstile or reCAPTCHA defeat tooling to scrape third parties.** That is not a scope this skill has, and it is not a capability the estate wants to own: the recurring maintenance tax of that arms race is larger than the retrieval bill it would be dodging, and Exa is already connected and free for search and extract. Retrieval questions route to `web-fanout`; this skill is actuation, which is a different problem.

## Where this sits against the other browser skills

`browser-routing` remains the entry point for "which browser tool for this job". This is the actuation tier: driving a real browser like a human inside one authenticated site. It does not replace a retrieval layer and is not a scraping substrate.

## Specialised skills

Load a specialised skill when the task falls outside browser web pages:

```bash
agent-browser skills get electron          # Electron desktop apps (VS Code, Slack, Discord, Figma, ...)
agent-browser skills get slack             # Slack workspace automation
agent-browser skills get dogfood           # Exploratory testing / QA / bug hunts
agent-browser skills get vercel-sandbox    # agent-browser inside Vercel Sandbox microVMs
agent-browser skills get agentcore         # AWS Bedrock AgentCore cloud browsers
```

Run `agent-browser skills list` to see everything available on the installed version.

## Observability dashboard

The dashboard runs independently of browser sessions on port 4848 and can also be opened through a proxied or forwarded URL such as `https://dashboard.agent-browser.localhost`. Stay on the dashboard origin: session tabs, status and stream traffic are proxied internally, so session ports do not need to be exposed.
