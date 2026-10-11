> Moved from SKILL.md. Read when setting up the GitHub Actions visual-regression workflow.

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
