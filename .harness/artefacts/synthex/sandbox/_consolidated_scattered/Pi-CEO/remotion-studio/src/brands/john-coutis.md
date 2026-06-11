# John Coutis OAM Design System

> Projection of `john-coutis.ts` + `john-coutis.design.md`. Source of truth: `Synthex/packages/brand-config/src/brands/john-coutis.ts` and `john-coutis.design.md`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *Half a Body, Full of Life.*

## 1. Visual Theme & Atmosphere

Warm, lived-in, earned. The system reads like a master storyteller's stage at the moment the houselights come down — charcoal surface, a single shaft of Australian gold for the call-to-action, condensed display type that mirrors his existing wordmark. Voice is `humorous + vulnerable + direct + warm + human`, cadence is short. Audience reads at grade ~5 — speaks the way tradies read. Nothing in the visual system competes with the man on camera; it exists to frame him, not to perform alongside him.

This is intentionally NOT the corporate-speaker visual default. It carves out airspace away from the navy-blue every other inspirational speaker uses and signals that John's authority is lived experience, not credentials.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#1A1A1A` (deep charcoal — dark hero surface) |
| Secondary | `colour.secondary` | `#3A2E1F` (warm umber — depth steps + card surfaces) |
| Accent | `colour.accent` | `#D4A437` (Australian gold — CTAs, OAM badge, pull-quote rules) |
| Neutral 50 | `colour.neutral.50` | `#F5F0E6` (warm cream — body text on dark) |
| Neutral 100 | `colour.neutral.100` | `#E8DFCE` (aged paper — secondary body) |
| Neutral 500 | `colour.neutral.500` | `#7A6F5C` (warm grey — inactive states) |
| Neutral 900 | `colour.neutral.900` | `#1A1A1A` (same as primary by design) |
| Success | `colour.semantic.success` | `#3FA34D` |
| Warning | `colour.semantic.warning` | `#E0A800` |
| Danger | `colour.semantic.danger` | `#C0392B` |
| Family | `colour.family` | `consumer` |

WCAG AA verified for all on-* pairings (on-primary, on-secondary, on-accent all pass AAA for normal text). No dark-variant defined — the system is dark-default.

## 3. Typography Rules

- **Display: Bebas Neue (SIL Open Font License)** — condensed, all-caps. Used for hero titles, chyron names, episode card headlines. Never set in mixed case.
- **Body: Inter (SIL Open Font License)** — workhorse. All non-display text: subtitles, captions, lower-thirds metadata, blog copy, on-screen lists.
- **Pull-quote: Inter italic 500** — when JC says something quotable on camera. The ONLY place italic appears in the system.
- No mono. No serif.

Headlines structurally aligned with his existing wordmark; body relaxed (1.55 line-height) for readability of long-form captions and on-screen quotes.

## 4. Component Stylings

- **Primary CTA**: Gold (`#D4A437`) on charcoal text, 4px radius. One per scene. Used for "Watch the talk", "Book John", "Subscribe".
- **Secondary CTA**: Outline-only (1px cream border on transparent). Used for "Read more", "See episodes".
- **Card**: Warm umber (`#3A2E1F`) surface, cream text, 8px radius. Episode tiles, testimonial blocks, topic cards.
- **Chyron**: Lower-third for video. Charcoal background, 6px gold left-rule, name in Bebas Neue caps, "OAM" post-nominal in caption typography on a second line.
- **Pull-quote-block**: Gold italic Inter with a 4px gold left-rule. The single emphatic punctuation device in editorial.
- **OAM Badge**: Small gold pill, charcoal text, caption typography, all-caps. Used in chyron and speaker intro stills.

## 5. Layout Principles

- 12-column grid, 112px outer margin landscape / 56px portrait.
- Headlines hold the top half of the frame.
- Wordmark logo top-left at minimum 56px height (`safeAreaPx`), never overlapping the subject.
- CTA chip always in the lower-right safe area.
- JC's face / skateboard never crops below the chest — he is framed at conversational eye level, not looked down at or up to.
- Safe-area inset: 5%.

## 6. Depth & Elevation

Flat-first. Warmth and depth come from the dual-tone charcoal+umber stack, not from drop shadows.

- Default elevation (when genuinely required): `0 4px 16px rgba(0, 0, 0, 0.32)`.
- Hero accent (one card per scene maximum): `0 8px 24px rgba(212, 164, 55, 0.18)` — barely-visible gold spill.
- Never decorative. Never stacked multi-layer.

## 7. Do's and Don'ts

**Do:**
- Frame JC at conversational eye level. He is a peer, not a monument.
- Lead with humour or vulnerability — never with hardship-as-headline.
- Use the gold accent sparingly: one CTA OR one pull-quote OR one OAM badge per scene, not all three.
- Set display type in Bebas Neue uppercase.
- Speak the way the audience reads (Flesch-Kincaid target grade 5).

**Don't (from `voice.forbiddenWords` + `doNot` + design rules):**
- Never frame his life as tragedy first — humour and agency come before hardship in every opening line.
- Never use pity language: `suffers`, `suffered`, `unfortunate`, `poor`.
- Never use medical / clinical disability terminology — his framing is lived, not diagnosed.
- Never reverse the vulnerable→lesson order.
- Never self-apply the label "inspirational" — that is what audiences say about him, not what the brand claims.
- Never strip the OAM post-nominal from formal speaker introductions.
- Never use stock disability imagery (wheelchair icons, ramps, accessibility symbols). His mode of motion is a custom skateboard.
- Never use Lucide / Material / FontAwesome icon families. Custom geometric marks only.
- Never set Bebas Neue in mixed case or below 32px.
- Never put gold on cream — contrast collapses.
- Never use red as an editorial colour. Red is `danger` state only.
- Banned words: `we`, `our`, `i`, `us`, `my`, `amazing`, `incredible`, `miraculous`, `miracle`, `unlock`, `journey`, `best self`, `limitless`, `unstoppable`, `world-class`, `game-changer`, `inspite`, `despite`, `wheelchair-bound`, `confined`, `disabled` (as a noun).

## 8. Responsive Behavior

Aspect ratios: `1920×1080` (landscape), `1080×1080` (square), `1080×1920` (portrait).

| Ratio | Display-xl | Display-md | Body-lg | Body-md |
|---|---|---|---|---|
| 1920×1080 | 128px | 56px | 20px | 16px |
| 1080×1080 | 96px | 48px | 18px | 16px |
| 1080×1920 | 84px | 44px | 18px | 16px |

CTA always above the safe-area fold in portrait. Chyron always within the lower 22% of the frame.

## 9. Agent Prompt Guide

- **Voice**: humorous + vulnerable + direct + warm + human; short cadence; reading-level target grade 5.
- **Default channel**: YouTube (largest unclaimed channel — currently dormant `@johncoutis3362`).
- **Voiceover**: He IS the voice on-camera. For B-roll / chyron narration only: ElevenLabs `EXAVITQu4vr4xnSDxMaL` (Sarah, en-AU, conversational style) as placeholder until licensed JC voice-clone exists.
- **Signature motion**: `rise` (vertical settle — mirrors the way he commands a stage by waiting before he speaks). Base 28 frames @ 30fps, transition 20 frames.
- **Example prompt**: *"Open on a charcoal (`{colors.primary}`) full-bleed scene. Lift the title 'NEVER GIVE UP MATE' in Bebas Neue 128px caps from `{colors.neutral-50}`, using `motion.signature: 'rise'` over 28 frames. After 2s, fade in the OAM badge in `{colors.accent}` to the right of his name. CTA chip 'WATCH THE TALK' in gold in the lower-right safe area."*

---

**Visual school anchor (single citation per CONTRACT.md)**: This system draws spiritual inspiration from Apple's WWDC keynote-recap aesthetic (dark hero, single accent, condensed display type as performer-frame) — adapted for warmth and Australian register. See `remotion-studio/src/design-systems/_library/` for the broader DESIGN.md reference set.
