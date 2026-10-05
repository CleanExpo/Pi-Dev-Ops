---
name: nextjs-image-seo
description: Use when optimising images in a Next.js / React codebase for SEO or
  accessibility — adding priority to above-fold next/image components, applying
  aria-hidden to decorative SVGs in JSX, or converting logo assets to WebP.
  Triggers on "priority prop", "aria-hidden svg", "decorative svg", "logo WebP",
  "next/image LCP", or "image SEO Next.js".
---

# Next.js Image SEO Patterns

## Overview

Three concrete patterns for Next.js image SEO that differ from general HTML advice:
`next/image` has its own `priority` prop, JSX SVGs need `aria-hidden` not `role="presentation"`,
and logo WebP can be served directly without `<picture>` when Next.js Image Optimisation handles fallback.

---

## Pattern 1 — `priority` on above-fold `next/image`

Add `priority` to every `<Image>` that is above the fold on initial load (logo, hero image, OG thumbnail).
This instructs Next.js to preload the image and skip the `loading="lazy"` default.

```tsx
// ✅ Good — logo always above fold
import Image from "next/image";

<Image
  src="/logo.png"
  alt="Restore Assist"
  width={100}
  height={100}
  priority                          // <-- add this
  className="object-contain p-1"
/>
```

**Where to check:** header components, hero sections, any `<Image>` in the first viewport.

**Do NOT add `priority` to:** below-fold images, gallery images, thumbnails in lists.

---

## Pattern 2 — `aria-hidden="true"` on decorative SVGs in JSX

Decorative SVGs (background blobs, geometric shapes, ornamental dividers) must be hidden from the
accessibility tree. In JSX this means `aria-hidden="true"` on the `<svg>` element itself.

```tsx
// ✅ Good — background shape, no semantic meaning
<svg
  aria-hidden="true"               // <-- required for decorative SVGs
  className="absolute top-1/3 right-1/4 w-96 h-96 opacity-20"
  viewBox="0 0 200 200"
>
  <path d="M40 ...Z" fill="currentColor" />
</svg>

// ✅ Good — play button inside a div that already carries aria-label
<div aria-label="Play video">
  <svg aria-hidden="true">        // <-- safe: parent div is the semantic element
    <polygon points="..." />
  </svg>
</div>

// ❌ Wrong — icon with semantic meaning, DO NOT hide
<svg aria-label="Close dialog" role="img">...</svg>
```

**How to identify decorative SVGs:**
- Positioned absolutely (`className="absolute ..."`) — almost always decorative
- Background shapes, blobs, gradients
- Duplicate visual elements (e.g. multiple wave dividers)
- SVGs inside a parent that already has `aria-label`

**Do NOT add `aria-hidden` to:** navigation icons, action button icons (Lucide/Heroicons in buttons),
meaningful illustrations with descriptive `aria-label`.

---

## Pattern 3 — Logo as WebP (Next.js Image Optimisation)

For logos served via `next/image`, Next.js automatically converts PNG → WebP/AVIF at the CDN edge.
No `<picture>` element needed; just point `src` at the WebP file if you have one.

```tsx
// Option A — let Next.js optimise PNG automatically (zero effort)
<Image src="/logo.png" ... />
// → Vercel/Next.js serves as WebP to supporting browsers automatically

// Option B — explicit WebP for full control
<Image src="/logo.webp" ... />
// → create public/logo.webp from design assets
// → keep public/logo.png for manifest.json / favicon only
```

**When to pick Option B:** when you want to audit exactly which format is served, or when
the image is used outside `next/image` (e.g. in an `<img>` tag or OG meta tag).

---

## Quick Reference

| Goal | Prop / Attribute | Element | Notes |
|------|-----------------|---------|-------|
| Prioritise LCP image | `priority` | `<Image>` (next/image) | Above-fold only |
| Hide decorative SVG | `aria-hidden="true"` | `<svg>` | No semantic meaning |
| Modern format | `src="/logo.webp"` | `<Image>` | Or let Next.js auto-optimise |
| Prevent lazy load on LCP | `priority` | `<Image>` | Removes `loading="lazy"` |
| Async decode non-LCP | `fetchPriority="low"` | `<img>` (raw) | Not needed for `next/image` |

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Adding `priority` to every image | Only above-fold images — priority on all = no priority |
| `role="presentation"` on SVG in JSX | Use `aria-hidden="true"` — React does not pass `role="presentation"` to SVGs the same way |
| `aria-hidden` on interactive SVG icon | Check parent — if `<button>` has accessible text, icon needs `aria-hidden`; if not, it needs `aria-label` |
| `loading="lazy"` AND `priority` together | Remove `loading="lazy"` — `priority` already disables lazy loading |
| Adding `alt=""` to `<svg>` | SVGs don't use `alt`; use `aria-hidden="true"` or `aria-label` |
