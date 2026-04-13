---
name: brand-ambassador
description: Generate brand-consistent content, copy, and messaging aligned with Pi-CEO tone and values.
automation: manual
anthropic_skill: anthropic-skills:brand-ambassador
intents: content
---

# Brand Ambassador Skill

Generates on-brand copy, product descriptions, social content, and documentation
that matches the Pi-CEO voice: direct, technical, no AI filler words, first-person
avoided, every sentence answers a specific question.

## When to use

- Writing product announcements, release notes, or sprint summaries
- Generating social content about Pi-CEO capabilities
- Drafting onboarding copy for the dashboard

## Usage

This skill is backed by the Anthropic Cloud Skill `anthropic-skills:brand-ambassador`.
Invoke via the Skill tool or reference in a brief:

```
Use the brand-ambassador skill to write a release announcement for Sprint 9.
```

## Tone constraints

- No first-person business language (We/Our/I/Us/My)
- No AI filler (delve, tapestry, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
- Technical accuracy over marketing language
