---
name: visual-qa
description: Playwright-powered visual testing skill. Captures screenshots at multiple breakpoints and colour schemes, runs visual regression tests, validates design implementation against DESIGN.md, and generates baseline snapshots for CI.
automation: manual
intents: design, review, test
---

# Visual QA Skill

The verification layer of the design stack. Takes screenshots, diffs them against baselines,
and catches visual regressions before they reach production.

**Requires Playwright installed:** `npx playwright install chromium`

---

## Quick Commands

### Capture inspiration (competitor / reference sites)
```bash
# Full desktop screenshot
npx playwright screenshot https://linear.app linear-desktop.png \
  --full-page --viewport-size "1440, 900"

# Dark mode + mobile
npx playwright screenshot https://stripe.com stripe-mobile-dark.png \
  --color-scheme dark --device "iPhone 14 Pro"

# Multiple breakpoints in parallel
for size in "375,812" "768,1024" "1280,800" "1920,1080"; do
  w=${size%,*}; h=${size#*,}
  npx playwright screenshot https://myapp.vercel.app "screen-${w}.png" \
    --viewport-size "$w, $h" --full-page &
done; wait
```

### Capture current implementation
```bash
# Dev server (wait for fonts/animations to settle)
npx playwright screenshot http://localhost:3000 current.png \
  --full-page --wait-for-timeout 2000 --viewport-size "1440, 900"

# Vercel preview URL
npx playwright screenshot https://my-app-git-branch.vercel.app preview.png \
  --full-page --ignore-https-errors
```

### Generate PDF (full-page design documentation)
```bash
npx playwright pdf http://localhost:3000 design-review.pdf
```

---

## Visual Regression Setup

### playwright.config.ts (Pi-CEO standard config)
```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/visual',
  snapshotDir: './tests/visual/__snapshots__',
  expect: {
    toHaveScreenshot: {
      threshold: 0.15,           // YIQ colour diff tolerance
      maxDiffPixelRatio: 0.005,  // max 0.5% of pixels may differ
      animations: 'disabled',    // freeze animations before capture
    }
  },
  projects: [
    { name: 'chromium-desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
    { name: 'chromium-mobile',  use: { ...devices['iPhone 13'] } },
    { name: 'dark-mode',        use: { colorScheme: 'dark', viewport: { width: 1280, height: 800 } } },
  ],
});
```

### Standard visual test template
```ts
// tests/visual/dashboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard visual regression', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.evaluate(() => document.fonts.ready); // wait for web fonts
    await page.waitForLoadState('networkidle');
  });

  test('homepage — full page', async ({ page }) => {
    await expect(page).toHaveScreenshot('homepage.png', { fullPage: true });
  });

  test('session card — default state', async ({ page }) => {
    const card = page.locator('[data-testid="session-card"]').first();
    await expect(card).toHaveScreenshot('session-card-default.png');
  });

  test('session card — hover state', async ({ page }) => {
    const card = page.locator('[data-testid="session-card"]').first();
    await card.hover();
    await expect(card).toHaveScreenshot('session-card-hover.png');
  });

  test('status badges — all variants', async ({ page }) => {
    const badges = page.locator('[data-testid="status-badges-demo"]');
    await expect(badges).toHaveScreenshot('status-badges.png');
  });
});
```

### Update baselines (after intentional design change)
```bash
npx playwright test --update-snapshots
# Always run baseline generation in CI (Linux) — not on macOS/Windows
# macOS font rendering differs → baselines generated locally will fail in CI
```

---

## Multi-Device Screenshot Matrix

Run this before shipping any design change:

```bash
# Standard 4-breakpoint matrix
for config in \
  "375,812,mobile" \
  "768,1024,tablet" \
  "1280,800,desktop" \
  "1920,1080,wide"; do
  w=${config%%,*}; rest=${config#*,}; h=${rest%%,*}; label=${rest#*,}
  npx playwright screenshot http://localhost:3000 "qa-${label}.png" \
    --full-page --viewport-size "$w, $h" --wait-for-timeout 1500
done

# Dark + light
npx playwright screenshot http://localhost:3000 qa-desktop-dark.png \
  --full-page --viewport-size "1280, 800" --color-scheme dark
```

---

## Font Load Verification

**Always wait for fonts before capturing:**
```ts
// In Playwright test
await page.evaluate(() => document.fonts.ready);

// Or wait for specific font
await page.evaluate(() => document.fonts.load('16px Geist'));
```

**Font regression — tight threshold:**
```ts
// Typography changes very little, so use tighter threshold
await expect(page.locator('h1')).toHaveScreenshot('heading.png', {
  threshold: 0.05,             // very tight — font rendering should be stable
  maxDiffPixels: 10,
  animations: 'disabled',
});
```

---

## Design vs Implementation Diff Workflow

1. **Capture reference:** Screenshot the design target (Figma export, competitor site, DESIGN.md preview.html)
2. **Capture implementation:** Screenshot the built component at same viewport
3. **Visual diff:** Feed both screenshots to a vision model with the prompt:
   ```
   Compare these two screenshots. List every visible difference in:
   1. Spacing and alignment
   2. Typography (size, weight, colour)
   3. Colour (compare against DESIGN.md tokens)
   4. Missing states
   5. Proportion differences
   ```
4. **Fix and re-capture** until diff is negligible

---

## CI Integration (GitHub Actions)

```yaml
# .github/workflows/visual-regression.yml
name: Visual Regression

on:
  pull_request:
    paths: ['dashboard/**', 'DESIGN.md']

jobs:
  visual:
    runs-on: ubuntu-latest  # ALWAYS Linux for consistent baselines
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npx playwright install chromium
      - run: npx playwright test tests/visual/
        env:
          BASE_URL: ${{ secrets.VERCEL_PREVIEW_URL }}
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: visual-diff-report
          path: playwright-report/
```

---

## When to Use Each Tool

| Task | Tool |
|------|------|
| Capture design inspiration | `playwright screenshot` CLI |
| Verify responsive breakpoints | Multi-device matrix script |
| Catch visual regressions in PR | `toHaveScreenshot()` in CI |
| Validate font rendering | Font-load wait + tight threshold test |
| Compare design vs implementation | Side-by-side screenshots → vision model |
| Full-page design documentation | `playwright pdf` |
| Animated component validation | Trace viewer (`npx playwright show-trace`) |

---

## Anti-Patterns in Visual Testing

- **Generating baselines on macOS** — font hinting differs from Linux CI → false failures
- **No `document.fonts.ready` wait** — FOUT (Flash of Unstyled Text) in screenshots
- **Animating during capture** — always disable animations in screenshots
- **Not masking dynamic content** — timestamps, session IDs, live data will diff on every run
  ```ts
  mask: [page.locator('.timestamp'), page.locator('[data-testid="session-id"]')]
  ```
- **Threshold too loose** — `threshold: 0.5` masks real regressions
- **No artifact upload on failure** — without the diff report, failures are impossible to debug
