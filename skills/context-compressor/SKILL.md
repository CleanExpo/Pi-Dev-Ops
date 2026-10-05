---
name: context-compressor
description: Compress context at tier boundaries to save tokens. Use when context is growing too large and needs shrinking at tier boundaries (such as handing work between tiers) to save tokens, choosing between truncating to first and last N characters, extracting keyword-relevant sections, or generating a cheap Haiku summary.
---

# Context Compressor

## Strategies
1. Truncate - Keep first/last N chars (free)
2. Extract - Pull keyword-relevant sections (free)
3. Summarize - AI summary via Haiku (cheap)
