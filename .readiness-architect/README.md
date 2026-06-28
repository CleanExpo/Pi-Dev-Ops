# Readiness Architect

`readiness-architect` is the universal front-door skill for turning a rough project or product request into a complete `/spm`-ready readiness scope.

It is designed to be used before `/spm`, `/judge`, `/goal`, `/session-handoff`, and `/resume-from-handoff`.

## Claude Code

```text
/reload-skills
/readiness-architect RestoreAssist final client-purchase readiness
```

## Codex

```text
$readiness-architect RestoreAssist final client-purchase readiness
```

Or:

```text
/skills
```

Then select `readiness-architect`.

## Command chain

```text
/readiness-architect <project or task>
/spm <generated scope>
/judge <generated SPM spec>
/goal <accepted implementation goal>
/session-handoff
/resume-from-handoff
```

## Purpose

This skill prevents broad, vague, bloated build requests from going straight into implementation.

It forces the request to be converted into measurable readiness gates before any build work starts.

## Default behaviour

Read-only.

The skill does not implement code, change files, commit, push, deploy, migrate, mutate tickets, change external systems, approve a build, or declare Shipit.

## Supported project types

- SaaS app
- Mobile app
- Desktop/web app
- Authority site
- CRM / operating system
- Contractor/member network
- Training platform
- Marketing / SEO / GEO engine
- Internal automation platform
- AI agent system
- E-commerce / paid product
- Client portal
- Public lead-generation site
- Hybrid ecosystem

## Output

The default output is a copy-paste `/spm` prompt that includes:

- Project classification
- Scope correction
- Specialist board
- Readiness gates
- Evidence policy
- Forbidden claims
- Acceptance criteria
- `/goal` command
- Final command workflow

## Safety rules

The skill must mark uncertain claims as:

```text
UNKNOWN
REQUIRES OWNER CHECK
HUMAN APPROVAL REQUIRED
UNSUPPORTED
```

It must block unsupported claims such as guaranteed revenue, guaranteed leads, guaranteed insurance outcomes, national coverage unless evidenced, certified status unless evidenced, and production readiness unless verified.
