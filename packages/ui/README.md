# @unite-group/ui

Shared UI primitives (shadcn New York template, React 19, Tailwind 4) for the Unite-Group portfolio. Consumed by Pi-CEO Dashboard, RestoreAssist, Synthex, DR-NRPG. Source of brand tokens: `@unite-group/brand-config` (`themeFactory(brand)`).

## Seed components

- Button (with `touch` size for WCAG 2.5.5 AAA 44×44px targets — RA-1578 lineage)
- Card (with `card-action` slot for header CTAs)
- Dialog (Radix + shadcn close button + nested header/footer)
- Form (react-hook-form integration + Radix Label)

## Install

This is a private workspace package. From a consuming app:

```json
"dependencies": {
  "@unite-group/ui": "file:../packages/ui",
  "@unite-group/brand-config": "file:../packages/brand-config"
}
```

Run `npm install` in the consuming app, then `npm run build` in this package.

## Use

```tsx
import { Button } from "@unite-group/ui";
import { themeFactory } from "@unite-group/brand-config/theme-factory";

const theme = themeFactory("ra");
```

## Build

```
cd packages/ui && npm install && npm run build
```

Outputs CJS + ESM + .d.ts to `dist/`.

## Roadmap

- More primitives: Input, Select, Tabs, Toast (Wave 2 / 2.5).
- Migrate Pi-CEO Dashboard from local components to consume this package (RA-1962 / 2.4 follow-up).
- DR-NRPG migration runs from Windows per machine-split (separate ticket).
