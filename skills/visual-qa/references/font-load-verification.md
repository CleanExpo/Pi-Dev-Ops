> Moved from SKILL.md. Read when screenshots may be taken before web fonts have loaded.

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
