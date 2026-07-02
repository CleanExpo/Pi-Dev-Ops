---
name: margot-routing
description: Linear routing checklist for Margot — place broad ideas in the parent project first, then copy to vertical projects only where scope belongs. Use when Margot creates tickets, triages founder ideas, or spans portfolio repos.
owner_role: Margot
status: active
---

# margot-routing

Cross-project routing hygiene for Margot (RA-6814). Prevents duplicate or orphan tickets across the Unite portfolio.

## Golden rule

**One canonical parent ticket first.** Copy or link into vertical projects only when work is truly in scope for that repo.

## Routing checklist (run before every Linear create)

1. **Classify scope**
   - Single repo / single deploy surface → create in that repo's Linear project (see `.harness/projects.json`).
   - Cross-cutting product idea → create in **parent** project (Margot, Pi-Dev-Ops epic, or RestoreAssist umbrella) first.

2. **Pick project from SSOT**
   - Read `.harness/projects.json` — match repo name (case-insensitive) → `linear_team_id` + `linear_project_id`.
   - Pi-Dev-Ops harness work → team RestoreAssist, project **Pi - Dev - Ops**.
   - Margot persona / voice / Telegram → project **Margot**.
   - RestoreAssist product → project **RestoreAssist** (not Pi-Dev-Ops unless the change is in `CleanExpo/Pi-Dev-Ops`).

3. **Labels**
   | Intent | Label |
   |--------|--------|
   | Pi-CEO should build autonomously | `pi-dev:autonomous` |
   | Machine spec pipeline ship | `pi-dev:machine-ship` |
   | Needs human review before build | `pi-dev:needs-review` |
   | Blocked on session loss | `pi-dev:blocked-reason:session-lost` |

4. **Status**
   - Autonomous pickup requires status **Ready for Pi-Dev** or **Todo** (poller config) + correct label.
   - Never file harness/engineering work only in **Backlog** if autonomy should pick it up.

5. **Vertical copy (optional)**
   - After parent ticket exists, create **linked** child issues in vertical projects only for repo-specific slices.
   - Child description must reference parent ID (`RA-xxxx`).
   - Do not duplicate the full brief in every vertical — link + scoped delta only.

6. **Forbidden**
   - Same brief opened in 3+ projects without parent link.
   - Pi-Dev-Ops project for Synthex frontend work (use Synthex project).
   - Secrets, credentials, or rotation tasks assigned to autonomous build without `Manual Task` label.

## Quick reference (common targets)

| Repo / area | Linear project |
|-------------|----------------|
| CleanExpo/Pi-Dev-Ops | Pi - Dev - Ops |
| Margot / Hermes / voice | Margot |
| RestoreAssist app | RestoreAssist |
| Synthex | Synthex (team SYN) |
| Unite-Group site | Unite-Group |

## Validation before close

- [ ] Parent ticket exists (if multi-repo)
- [ ] Project matches `.harness/projects.json` for the repo that will change
- [ ] Labels match intended pickup path (autonomous vs manual)
- [ ] Description names acceptance criteria + repo path
