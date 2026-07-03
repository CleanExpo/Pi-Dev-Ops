# Unite-Group Nexus — Ecosystem Link

**This project is part of the Unite-Group Nexus.**

## What is the Nexus?

Unite-Group Nexus Pty Ltd (ABN 62 580 077 456, owner: Phill McGurk) operates a
hub-and-spoke ecosystem connecting property, finance, legal, and construction
services. One of the client ventures served by this ecosystem is Duncan
Perkins' referral network (Home Loan Essentials / duncanperkins.com, the ITR
Button product). This repository (Pi-Dev-Ops) provides the discovery
orchestration, provisioner, and Margot bots for the entire ecosystem.

## Full Ecosystem Map

See the central Nexus documentation in the ITR-Button repository:

**https://github.com/CleanExpo/ITR-Button/blob/main/docs/NEXUS.md**

## How This Project Fits

Pi-Dev-Ops is the **orchestration layer** of the Nexus. It contains:
- Discovery questionnaires (12Q, vision discovery)
- Client portal provisioner
- Telegram bot infrastructure (@PiCEODimitr_bot)
- Margot agentic operations

## Hub-and-Spoke Diagram

```
                    ┌─────────────────┐
                    │   ITR-Button    │
                    │  (tax entry)    │
                    └────────┬────────┘
                             │
    ┌──────────────┐    ┌────┴────┐    ┌──────────────┐
    │ Home Loan    │◄───┤  Unite  ├───►│  Lawyers     │
    │ Essentials   │    │  Group  │    └──────────────┘
    └──────────────┘    │  Nexus  │
                        │  HUB    │
    ┌──────────────┐    │         │    ┌──────────────┐
    │    Banks     │◄───┤         ├───►│  Financial   │
    │              │    └────┬────┘    │  Planners    │
    └──────────────┘         │         └──────────────┘
                             │
                    ┌────────┴────────┐
                    │ Architects /    │
                    │ Builders /      │
                    │ Developers      │
                    └─────────────────┘
```

Duncan Perkins' Home Loan Essentials / duncanperkins.com is the client-facing
intake point for this particular referral vertical — one spoke the Nexus
serves, not the hub itself.

## Related Repositories

| Repository | Role in Nexus |
|------------|---------------|
| [ITR-Button](https://github.com/CleanExpo/ITR-Button) | Tax return entry point + NOAH referral router |
| [DIY-Home-Loan](https://github.com/CleanExpo/DIY-Home-Loan) | Home loan journey |
| [brain-1](https://github.com/CleanExpo/brain-1) | Strategic memory and commercial terms |
| [Pi-Dev-Ops](https://github.com/CleanExpo/Pi-Dev-Ops) | Discovery orchestration (this repo) |
| [Unite-Hub](https://github.com/CleanExpo/Unite-Hub) | CRM / client portal |
| [Unite-Group](https://github.com/CleanExpo/Unite-Group) | Synthex Authority Hub |

---

*Last updated: 2026-07-03*
*Ownership corrected per founder direction: Unite-Group Nexus Pty Ltd (Phill
McGurk) is the owner/operator; Duncan Perkins is a client. Supersedes the
2026-05-31 draft, which was sourced from Duncan's own hand-drawn sketch of
his referral concept and mistakenly used as the top-level ownership doc.*
