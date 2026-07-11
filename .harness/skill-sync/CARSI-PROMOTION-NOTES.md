# CARSI Course Production Promotion Notes

## Promotion Review

- Source: `/Users/phill-mac/CARSI/.claude/skills/carsi-course-production/`
- Canonical destination: `skills/carsi-course-production/`
- Classification in scan report: `PROJECT_SPECIFIC`
- Folder SHA-256: `8a55693029b16e0f9b42691a5f1a92f0cef6b51ddcad7a301b8d282585b385bb`
- `SKILL.md` SHA-256: `a9c0947c66131a4a7a17c3375582d932f8cb70fc66719aa5f096bf2c4dd30561`
- Skill-authoring-standard review: PASS
- `SKILL.md` line count: 127, below the 200-line cap

## Preserved Controls

Promotion preserved the project-local text exactly. The canonical skill still requires:

- Australian English, metric units, AUD, Australian examples, Australian regulators, AS/NZS framing.
- 230 V nominal / 50 Hz, 10 A GPO, RCD/safety switch, test-and-tag terminology.
- Australian-available products and dated availability checks.
- IICRC CEC-only terminology and CARSI Southern Hemisphere Restoration Designations.
- Founder-gated production publish/unpublish flow.
- IICRC standards IP and AI-use restrictions.

## Enhancement Opportunities

These are intentionally deferred and were not folded into the promotion:

- Split branch-only CARSI operational details into `references/` if the skill grows past the current line budget.
- Add a CARSI-side wrapper or README that points collaborators at the canonical Pi-Dev-Ops skill once their global library is installed.
- Add a CARSI repository check that compares the project-local copy to the canonical skill during the transition period.

## Safest Treatment For The CARSI Project-Local Copy

Do not delete the CARSI project-local copy yet. Keep it temporarily so collaborators who have not installed the global Claude library are not broken, but treat Pi-Dev-Ops as canonical from this branch forward. The next safe CARSI-side change is a tiny wrapper/README update that points to `Pi-Dev-Ops/skills/carsi-course-production/` and optionally replaces the folder with a symlink after collaborator environments have run the global installer.
