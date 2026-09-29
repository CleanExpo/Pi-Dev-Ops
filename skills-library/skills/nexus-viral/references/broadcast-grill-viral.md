# Broadcast Grill (viral) — quality before publish

This extends video-director's Gate B with short-form-specific lenses. It runs on the hero
short before repurpose, and on each derived cut (captions/safe-zone only). It invokes
`lib/video/quality-gate`, writes a `marketing_agency_qa_reports` row, and emits an
`audit_events_immutable` entry. A FAIL is terminal for that asset. It never self-approves —
there is no path that hardcodes PASS.

## Lenses (each is pass/fail with a one-line reason)

1. **Thumb-stop.** Does frame 1 stop the scroll on its own? Fails on logos, slow fades,
   title cards, or a static opening.
2. **Hook lands ≤2s.** Is the promise/tension clear, spoken, and burned on screen within
   two seconds? Fails on "welcome back" intros or a hook that only arrives after setup.
3. **Retention shape.** Is there a new beat every ~1.5s with no dead middle (sec 3–5)?
   Fails if any beat only restates the previous one.
4. **Muted legibility.** Do burned captions carry the point fully muted, ≤2 lines,
   high-contrast, inside the safe zone? Fails if the payoff needs sound.
5. **Loop / close.** Does it resolve the hook and seed a rewatch/comment reason? Fails on
   an abrupt cut with no close or a CTA that buries the payoff.
6. **Safe zone.** Are faces/captions clear of the bottom ~15% and right ~12% platform UI?
7. **Disclosure.** Is AI/synthetic media disclosed per the campaign rules when used?
   Fails closed if synthetic and undisclosed.
8. **Claim integrity.** Every on-screen claim traces to evidence; no invented stats, view
   counts, or "as seen on". Inherits the campaign evidence gate.

## Remediation ladder (on FAIL)

1. **Re-caption / re-time** — cheapest; fixes lenses 4, 6 without regenerating.
2. **Re-cut the open** — swap frame 1 / tighten the hook (lenses 1, 2) by re-stitching beats.
3. **Regenerate the weak beat** — only the failing 1.5s beat, not the whole hero (lens 3).
4. **Bounce to Brief** — if the angle itself failed hookability, return to Stage 1 rather
   than polish a weak idea. A weak idea is a Brief problem, not a render problem.

## What the grill writes

- `marketing_agency_qa_reports` — per-lens result + overall PASS/FAIL + asset ref.
- `audit_events_immutable` — append-only record that the gate ran and its verdict.
- On PASS, the hero is promoted to `video_assets` and released to Stage 4 (repurpose).
