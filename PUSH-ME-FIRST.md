# PUSH-ME-FIRST — read this before anything else

You're looking at this file because something is wrong with the Pi-CEO rails. The single most common cause is **unpushed commits sitting on `main` that were supposed to fix the current bug.** Until you run `git push origin main` from a terminal with GitHub push credentials, Railway is running stale code and none of the "fixes I landed yesterday" are actually in production.

## One-minute triage

Run these three commands in order. Stop at the first one that says something's wrong.

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git fetch origin
git log origin/main..HEAD --oneline
```

If the third command prints nothing → `main` is pushed, move on to the next triage step.
If it prints anything → you have unpushed commits. Push them:

```bash
git push origin main
```

Then check `/health` on Railway and watch for `autonomy.armed: true` and a `poll_count` that increases every 5 minutes. If it does, the rails are back.

## The three things that must be true for overnight autonomy to work

1. **Every commit on local `main` is pushed to `origin/main`.**
2. **Railway has `LINEAR_API_KEY`, `ANTHROPIC_API_KEY`, and `TAO_AUTONOMY_ENABLED=1` in its env vars.**
3. **Railway `/health` returns `autonomy.armed: true`** (the fix from commit `e611b1c` onwards).

If any of those is false, autonomy is dead on arrival and you'll wake up to zero commits no matter how much I wrote in the charters the night before.

## Why this file exists

On 2026-04-11→12 the marathon rails ran overnight and produced zero commits. The root cause was that seven commits (including the self-start fix) were sitting unpushed on my local `main` while I (the Cowork Pi-CEO process) didn't have push credentials. The fix was a one-line `git push` from Phill's Mac — the step that was documented only as a footnote at the bottom of a Telegram message.

This file is my apology and my correction. Any time Pi-CEO changes something that matters to the rails, the first question to ask is "is it pushed?" — and this file is the reminder that that question exists.

See `.harness/INCIDENT-2026-04-12.md` for the full post-mortem.
See `.harness/ARCHITECTURE-V2.md` for the plan to remove this class of failure permanently.
