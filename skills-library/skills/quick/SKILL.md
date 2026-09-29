---
name: quick
description: Use when the user says "/quick", "/quick 3", "give me the short version", "just the takeaways", or "bullet it". Compresses the previous answer into a small numbered list of the most important points.
---

# /quick — the short version

Compress your **previous message** into a numbered list of the most important
points, ranked most important first.

## How many

- `/quick 3` → exactly 3 points. Whatever number is given, give exactly that.
- `/quick` with no number → give 3, unless the content genuinely has fewer real
  points, in which case give what exists and say so.

Never pad to reach the number. If there are only 2 real points, say "only 2
things actually matter here" and give 2.

## Shape

- One line per point. A full sentence, not a fragment.
- Lead each point with the thing itself, not with preamble.
- Plain words. No jargon that was not already explained.
- Keep exact numbers, SHAs, file names and verdicts inside the point.

## After the list

If something important had to be left out, add one final line starting with
"Left out:" and name it. A short answer that hides a blocker is worse than a
long one.

## Do not

- Do not restate the whole message in bullet form. This is selection, not
  reformatting.
- Do not add new findings or new work.
