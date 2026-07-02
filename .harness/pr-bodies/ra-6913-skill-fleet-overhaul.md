## Summary

Unblocks RA-6913 — fleet-wide SKILL.md hygiene so all 143 skills load with valid frontmatter, portable paths, and correct repo-root refs.

- **Defect 1:** Added YAML frontmatter to `skills/pi-dev-linear-contract/SKILL.md` (was the sole skill without it; empty description broke upload/routing quality).
- **Defect 2:** Fixed dangling refs in `launch-charter` (`../../AGENTS.md`, `../../CLAUDE.md`) and remotion skills (repo-relative `../../app/server/...`, `../../remotion-studio/...`).
- **Defect 3:** Replaced `/Users/phill-mac` → `~` across 23 skills for sandbox/CI portability. Encoded Claude memory pointers (`~/.claude/projects/-Users-phill-mac-...`) unchanged.

27 files, +53/−48. Docs-only — zero runtime code paths.

## Verification

```bash
# 143/143 frontmatter
python3 -c "from pathlib import Path; assert not [p.parent.name for p in Path('skills').glob('*/SKILL.md') if not p.read_text().startswith('---')]"

# zero hardcoded Mac paths
rg '/Users/phill-mac' skills/*/SKILL.md  # → 0 matches

# loader
python3 -c "from src.tao.skills import load_all_skills, invalidate_cache; invalidate_cache(); s=load_all_skills(); assert len(s)==143; assert len(s['pi-dev-linear-contract']['description'])>=20"

python -m pytest tests/test_autonomy_contract.py tests/test_spm_skill.py -q  # 10 passed
```

## Manual verification path

1. Open `skills/pi-dev-linear-contract/SKILL.md` — confirm `---` frontmatter with `name:` + `description:`.
2. Open `skills/launch-charter/SKILL.md` — click `../../AGENTS.md` link resolves to repo root.
3. `rg '/Users/phill-mac' skills/` — expect no matches.

## Test plan

- [x] AC1: 143/143 frontmatter
- [x] AC2: launch-charter + remotion refs resolve
- [x] AC3: zero `/Users/phill-mac` in skills
- [x] AC4: body content unchanged except refs/paths/frontmatter
- [x] pytest autonomy_contract + spm_skill green

## Linear

Closes RA-6913
