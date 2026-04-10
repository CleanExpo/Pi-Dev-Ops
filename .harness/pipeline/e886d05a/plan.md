```markdown
# Plan: Dark mode toggle in dashboard settings
**Pipeline:** e886d05a
**Effort:** M
**Date:** 2026-04-10

## Approach
Adopt Tailwind's `darkMode: 'class'` strategy and replace the 10 hardcoded hex tokens in `tailwind.config.ts` with CSS custom property references (`var(--color-*)`). CSS custom properties switch automatically when `.dark` is present on `<html>`, so no per-element `dark:` utility class changes are required. A synchronous inline `<script>` injected into `<head>` in the root layout reads `localStorage` and stamps `class="dark"` on `<html>` before the first paint, satisfying the FOUC acceptance criterion. A client-side `ThemeProvider` context manages toggle state and `localStorage` persistence; `SettingsForm` consumes it to render the Appearance toggle.

The existing Bloomberg dark aesthetic is mapped to `.dark` custom property values; `:root` carries the light values. Default on first visit is dark (FOUC script applies `.dark` when no preference is stored), matching AC5.

## Files Changed
| File | Change Type | Why |
|------|------------|-----|
| `dashboard/tailwind.config.ts` | modify | Add `darkMode: 'class'`; replace 10 hex values with `var(--color-*)` references |
| `dashboard/app/globals.css` | modify | Define `:root` (light) and `.dark` (dark/Bloomberg) CSS custom property sets; fix hardcoded `html, body` hex values |
| `dashboard/components/ThemeProvider.tsx` | create | Client context provider exposing `theme` and `toggleTheme`; persists to `localStorage['pi-theme']` |
| `dashboard/app/layout.tsx` | modify | Import `ThemeProvider`; add FOUC-prevention `<script nonce={nonce}>` in `<head>` before body |
| `dashboard/app/(main)/layout.tsx` | modify | Replace 4 hardcoded inline `style` hex values with Tailwind semantic classes (`bg-bg`, `border-border`, etc.) |
| `dashboard/app/(main)/settings/page.tsx` | modify | Remove hardcoded `style={{ background: "#0A0A0A" }}`; use Tailwind `bg-bg` class |
| `dashboard/components/SettingsForm.tsx` | modify | Add Appearance section with theme toggle; consume `useTheme()`; replace `inputStyle` hex values with CSS-var-backed equivalents |

## Implementation Steps

1. **tailwind.config.ts** — add `darkMode: 'class'` at top level; replace every hex value in `theme.extend.colors` with its `var(--color-{token})` counterpart (e.g. `bg: "var(--color-bg)"`, `panel: "var(--color-panel)"` … 10 tokens total)

2. **globals.css** — add `:root {}` block with light-theme values for all 10 tokens (bright neutrals); add `.dark {}` block with the existing Bloomberg hex values (exact originals from `tailwind.config.ts`). Replace hardcoded `#0A0A0A` and `#F0EDE8` on `html, body` with `background-color: var(--color-bg)` and `color: var(--color-text)`. Mirror scrollbar and selection colours as CSS vars too.

3. **ThemeProvider.tsx** (new, `"use client"`) — define `ThemeContext` typed `{ theme: 'dark' | 'light'; toggleTheme: () => void }`. `useState` initialises to `'dark'` (SSR-safe). `useEffect` on mount: reads `localStorage.getItem('pi-theme')`, if `'light'` sets state to `'light'` and removes `.dark` from `document.documentElement`. `toggleTheme`: flips state, writes to `localStorage`, toggles `.dark` class on `document.documentElement`. Export `useTheme()` convenience hook. Under 40 lines.

4. **app/layout.tsx** — add `<head>` element containing `<script nonce={nonce} dangerouslySetInnerHTML={{ __html: fouc }}/>` where `fouc` is an IIFE: reads `localStorage.getItem('pi-theme')`; if not `'light'`, calls `document.documentElement.classList.add('dark')`. Import and wrap `<ToastProvider>` children with `<ThemeProvider>`. The `<html>` tag gains no static `class`; the FOUC script stamps it before paint.

5. **app/(main)/layout.tsx** — replace `style={{ borderBottom: "1px solid #2A2727", background: "#0A0A0A" }}` on `<nav>` with `className="bg-bg border-b border-border"`. Replace `style={{ color: "#E8751A" }}` on the π logo span with `className="text-orange"`. Replace `style={{ color: "#F0EDE8" }}` on "PI CEO" span with `className="text-text"`. Replace `style={{ color: "#888480" }}` on subtitle span with `className="text-chrome"`. Replace `style={{ color: active ? "#E8751A" : "#C8C5C0" }}` on nav links with conditional `className` using `text-orange` / `text-muted`. Remove `style={{ borderLeft: "1px solid #2A2727" }}` in favour of `border-l border-border`. (File stays well under 60 lines.)

6. **app/(main)/settings/page.tsx** — remove `style={{ background: "#0A0A0A" }}` from wrapper `<div>`; add `className="bg-bg"`. Remove `style={{ borderBottom: "1px solid #2A2727" }}` from header `<div>`; add `className="border-b border-border"`. Replace `style={{ color: "#C8C5C0" }}` and `style={{ color: "#888480" }}` with `className="text-muted"` and `className="text-chrome"`.

7. **SettingsForm.tsx** — add `import { useTheme } from "@/components/ThemeProvider"` at top. Replace `inputStyle` constant's hex values with CSS-var equivalents (e.g. `background: "var(--color-panel)"`, `color: "var(--color-text)"`, `border: "1px solid var(--color-border)"`). Add new `<Section title="Appearance">` block (before Credentials) containing a labeled toggle: calls `toggleTheme()` on click, displays current theme. Inline `style` colour hardcodes in `Badge`, `Field`, `Section`, and `save` button that map to existing semantic tokens should be converted to Tailwind classes using the new semantic names. File will reach ~295 lines — keep every function under 40 lines, extract toggle to a `<ThemeToggle>` sub-component if needed to stay under 300.

## Dependencies
- Must complete before starting: steps 1 and 2 must land before any component work (steps 3–7), because Tailwind will fail to compile `var(--color-*)` references until the CSS custom properties exist
- Unblocks: OS-level `prefers-color-scheme` auto-detection (follow-up ticket per spec non-goals)
- External: none — no new env vars, packages, or third-party services required

## Risks
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| `inputStyle` inline object not picked up by Tailwind JIT | Low | Low | Values use `var()` references — not Tailwind classes — so no purging issue; CSS vars resolve at runtime |
| FOUC script blocked by CSP `script-src` | Medium | High | Pass `nonce={nonce}` (already threaded through `app/layout.tsx` via `x-nonce` header) to the `<script>` tag |
| `SettingsForm.tsx` exceeds 300-line limit | Medium | Low | Extract `<ThemeToggle>` sub-component in same file if count reaches 295+ |
| `tailwind.config.ts` `var()` syntax breaks older Tailwind versions | Low | High | Verify Tailwind 3.x+ — `var()` in config `colors` is supported since v3.1 |
| Dark-mode regression on `(main)/layout.tsx` inline `style` removal | Low | High | Dark theme regression check: run `npm run build` and screenshot both themes on all 5 nav routes before merging |

## Test Plan
- **Unit:** `ThemeProvider.tsx` — test `toggleTheme` flips state between `'dark'` and `'light'`; test `localStorage` read on mount sets correct initial theme; test FOUC IIFE logic in isolation (pure function)
- **Integration:** Load `/settings` with `localStorage.getItem('pi-theme') === 'light'` set → assert `<html>` has no `.dark` class and computed `background-color` is the light `:root` value
- **Manual:** (1) Fresh browser (no localStorage) → dashboard loads in dark mode; (2) Toggle to light in Settings → entire app switches immediately; (3) Reload → light mode persists; (4) Navigate to DASHBOARD, BUILDS, CHAT, HISTORY routes → theme unchanged; (5) Toggle back to dark → app switches in < 100 ms
- **Regression:** `npm run build` must complete with 0 type errors; existing dark-mode visual appearance must be pixel-identical to pre-refactor screenshots on the dark path
```