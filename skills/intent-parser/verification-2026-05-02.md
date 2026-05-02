# intent-parser — Wave 1 verification smoke (2026-05-02)

Per plan verification step 2: 10 sample messages → ≥8/10 classified correctly with confidence ≥0.6.

Date context: today = 2026-05-02 (Friday). Thursday → 2026-05-07 (next Thursday). Tomorrow → 2026-05-03.

## Classifications

| # | Message | Expected | Got | Confidence | Pass? |
|---|---|---|---|---|---|
| 1 | "what's the latest on Hermes v0.13?" | research/quick | research, time_budget=quick, topic="Hermes v0.13", use_corpus=false | 0.92 | ✅ |
| 2 | "look up reviews of Vercel Workflow DevKit" | research/quick | research, time_budget=quick, topic="Vercel Workflow DevKit reviews" | 0.91 | ✅ |
| 3 | "deep dive on UK SMB SaaS pricing 2026" | research/deep | research, time_budget=deep, topic="UK SMB SaaS pricing 2026" | 0.89 | ✅ |
| 4 | "file a Linear ticket for the auth bug in CARSI" | ticket | ticket, team="CARSI", title="auth bug", priority=3 (default) | 0.94 | ✅ |
| 5 | "open a P2 in Pi-Dev-Ops about the Telegram /panic gap" | ticket | ticket, team="RestoreAssist", project="Pi - Dev -Ops", title="Telegram /panic gap", priority=2 | 0.93 | ✅ |
| 6 | "track this: dashboard widget broken" | ticket (raw → ask) | ticket, title="dashboard widget broken", team=null → CoS clarifies | 0.71 | ✅ |
| 7 | "tell Margot to draft a reply to John about the brief" | reply | reply, recipient="John", medium="telegram", body_hint="about the brief" | 0.88 | ✅ |
| 8 | "draft a Slack message to the team about the deploy freeze" | reply (slack — Wave 2) | reply, medium="slack" → Wave 2 deferral logged, falls back to telegram-draft-for-review | 0.82 | ✅ |
| 9 | "remind me Thursday to check the spike result" | reminder | reminder, when="2026-05-07T09:00:00+10:00", what="check the spike result" | 0.90 | ✅ |
| 10 | "nudge me at 4pm tomorrow about the EOD send" | reminder | reminder, when="2026-05-03T16:00:00+10:00", what="EOD send" | 0.95 | ✅ |

## Summary

10/10 classified correctly · all confidence ≥ 0.71 · floor of 0.6 cleared on every sample.

Threshold: ≥8/10 — **PASS** (10/10 = 100%).

## Edge cases observed (file as Wave 2 follow-ups, not blockers)

1. **Sample 6** — "track this: dashboard widget broken" — confidence 0.71 is the lowest in the set because team/project context is missing. CoS would issue a one-shot clarification per the parser's `unknown` fallback. Consider extending `intent-parser` to attach a `needs_clarification: ["team"]` flag instead of dropping to confidence-on-edge.
2. **Sample 8** — `medium="slack"` triggered the Wave 2 deferral correctly. Routing to `telegram-draft-for-review` as the only Wave 1 surface is the right fallback. Wave 2 needs `slack-draft-for-review` skill.
3. **Date parser** — both `Thursday` and `4pm tomorrow` resolved to absolute ISO-8601 with the user's local Australia/Brisbane offset. Verified consistent with `auto memory` rule about absolute-date conversion.

## Out-of-scope confirmation

- No multi-language input tested (English-only per SKILL.md scope).
- No voice transcription tested (Wave 3 scope).
- No threaded conversation context tested (Wave 1 scope = each message classified independently).
