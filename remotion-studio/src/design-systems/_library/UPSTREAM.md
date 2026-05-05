# Vendored design-systems library

138 portable `DESIGN.md` reference systems imported verbatim from `nexu-io/open-design` (Apache-2.0).

- **Upstream:** https://github.com/nexu-io/open-design/tree/main/design-systems
- **License:** Apache 2.0 — `LICENSE` at the upstream repo root applies to every file in this directory.
- **Imported:** 2026-05-05 (commit at `HEAD` on that date).

## Why this is here

Each subdirectory is a standalone `DESIGN.md` describing one well-known visual identity (claude, airbnb, brutalism, monocle, …). They are reference inputs for our brand workflow:

- `remotion-brand-codify` reads them as exemplars when emitting per-brand `DESIGN.md` projections.
- `remotion-designer` cites them as visual-school anchors in 5-D critique.
- Web frontends (Phase 2) import them as starter token sets.

Source of truth for our seven brands stays at `remotion-studio/src/brands/{slug}.ts` + sibling `{slug}.md`. The `_library/` directory is a vendored asset pool, not our brand state.

## Refresh

To pull a newer snapshot from upstream:

```sh
rm -rf src/design-systems/_library
git clone --depth 1 https://github.com/nexu-io/open-design.git /tmp/open-design
cp -R /tmp/open-design/design-systems/. src/design-systems/_library/
```

Do not edit files in this directory in-place — overwrites on refresh. Brand-specific edits go to `src/brands/`.
