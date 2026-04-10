The spec is ready. You need to grant write permission to `.harness/pipeline/e886d05a/spec.md` for it to be saved. Here's the full spec content:

---

```markdown
# Spec: Dark mode toggle in dashboard settings
**Type:** feature
**Pipeline:** e886d05a
**Date:** 2026-04-10

## Summary
Add a light/dark theme toggle to the dashboard settings page. The application currently hardcodes a dark Bloomberg terminal aesthetic using static Tailwind colour values. This spec covers refactoring those hardcoded values to CSS custom properties and wiring a toggle in the Settings UI that persists the user's preference to `localStorage`. Theme changes apply immediately without a page reload.

## Goals
- Allow users to switch between the existing dark theme and a new light theme
- Persist theme preference in `localStorage` under a `pi-theme` key
- Apply theme changes immediately on toggle without a page reload
- Restore the persisted theme on page load with no flash of unstyled content (FOUC)
- Add the toggle control to the existing Settings page (`/settings`)

## Non-Goals
- Automatic OS-level `prefers-color-scheme` detection (follow-up ticket)
- Per-component custom colour palette selection
- Supabase-backed preference sync across devices
- Theme scheduling (sunrise/sunset auto-switching)

## Acceptance Criteria
- AC1: Given the user is on the Settings page, when they click the dark/light mode toggle, then the entire dashboard switches theme immediately without a page reload
- AC2: Given the user has selected light mode, when they close and reopen the browser tab, then light mode is still active (preference loaded from `localStorage`)
- AC3: Given the user navigates between DASHBOARD, BUILDS, CHAT, HISTORY, and SETTINGS routes, then the selected theme persists across all routes
- AC4: Given the page is loading for the first time with a stored preference, then the correct theme is applied before the first paint (no visible FOUC)
- AC5: Given dark mode is active (the default), when no preference is stored in `localStorage`, then the dashboard renders in dark mode as today

## Constraints
- **Performance:** Theme switch must complete in < 100 ms; CSS variable swap must not trigger layout reflow
- **Security:** No server round-trip required for theme toggle; preference stays client-side only
- **Backward Compatibility:** Existing dark theme visual appearance must be pixel-identical to today after refactor; no style regressions on the dark path
- **Dependencies:** Tailwind CSS `darkMode: 'class'` strategy required — `tailwind.config.ts` must be updated before component work begins

## Files Changed
- `dashboard/tailwind.config.ts` — enable `darkMode: 'class'`; convert static colour tokens to CSS variable references
- `dashboard/app/globals.css` — define `:root` (light) and `.dark` CSS custom property sets for all colour tokens
- `dashboard/app/layout.tsx` — wrap with `ThemeProvider`; inject inline script to read `localStorage` and set `class` on `<html>` before first paint
- `dashboard/components/ThemeProvider.tsx` — new Context provider; exposes `theme` and `toggleTheme`; persists to `localStorage`
- `dashboard/app/(main)/layout.tsx` — replace hardcoded inline style props with Tailwind utility classes
- `dashboard/app/(main)/settings/page.tsx` — add theme toggle control (labeled "Appearance")
- `dashboard/components/SettingsForm.tsx` — render toggle UI using `useTheme()` hook

## Out of Scope
- Refactoring component-level inline `style` props beyond what is required for theme switching
- Adding animation/transition effects to the theme switch
- Dark mode support in email or Telegram notification templates
```

---

**Key findings that shaped this spec:**
- The dashboard is already dark — the "toggle" adds a *light* mode as the alternative
- All colours are hardcoded in `tailwind.config.ts` with no CSS variables, so a `darkMode: 'class'` refactor to CSS custom properties is the prerequisite
- The FOUC prevention inline script on `<html>` is explicitly called out as an AC — this is the most commonly missed implementation detail
- 7 files identified as needing changes, scoped tightly to avoid touching unrelated components