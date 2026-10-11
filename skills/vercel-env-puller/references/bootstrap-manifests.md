> Moved from SKILL.md. Read when seeding or refreshing the initial per-project manifests.

## Initial bootstrap manifests (Wave 5 #2 ships)

Per the recon — 9 projects to seed. Phase A ships these 9 manifests:

| project_slug | source repo | manifest priority |
|---|---|---|
| restoreassist | CleanExpo/RestoreAssist | High — already debugging Cloudinary + Xero today |
| pi-dev-ops | CleanExpo/Pi-Dev-Ops | High — Pi-CEO eats own dogfood |
| synthex | CleanExpo/Synthex | High — has Stripe + Anthropic |
| ccw-crm | CleanExpo/CCW-CRM | Medium |
| disaster-recovery | CleanExpo/DR-Sandbox | Medium |
| dr-nrpg | CleanExpo/DR-NRPG | Medium |
| nrpg-onboarding | CleanExpo/NRPG-Onboarding-Framework | Low |
| carsi | CleanExpo/CARSI | Low |
| unite-group | CleanExpo/Unite-Group | Low |

Initial seed: run `vercel env ls --json --environment=production` for each, classify auto, commit manifest, operator reviews PR before merge.
