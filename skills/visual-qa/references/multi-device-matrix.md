> Moved from SKILL.md. Read when capturing screenshots across the standard breakpoint and colour-scheme matrix.

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
