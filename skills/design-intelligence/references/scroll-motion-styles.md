Moved from SKILL.md. Read when a brief calls for a scroll-driven or 3D site and a motion style must be named.

## Scroll & motion styles (for animated / 3D sites)

When a brief calls for a scroll-driven or 3D site, name the motion style up front — pick one,
don't blend:

| Style | Motion |
|-------|--------|
| **A — Loop** | Hero animation loops with no visible seam; alive at rest, never freezes |
| **B — Scrub** | Scroll position scrubs a timeline (frames, not mp4 — WebP frames scrub smoother) |
| **C — Cursor** | Elements react to cursor position |
| **D — Horizontal** | Vertical scroll drives horizontal travel |
| **E — Exploded** | Parts assemble/disassemble on scroll |
| **F — Push-through** | Camera pushes through layered planes |
| **G — Scrollytelling** | Copy beats pinned to scroll milestones |

Motion render laws: locked camera, constant velocity, motion-blur off, `START = END` for any
loop. A frozen hero reads as broken.
