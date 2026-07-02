# PR: fix(margot): P0 go-live — inflight harvest, voice bridge, Telegram send, health

**Branch:** `fix/margot-p0-go-live`  
**Commit:** `1dacdcc7`

## Summary
- **Inflight harvest:** `swarm/margot_inflight.py` delivers completed `deep_research_max` results on the next `handle_turn` for the same Telegram `chat_id` (tags `margot_chat:{chat_id}` in inflight log).
- **Voice bridge:** `/api/margot/turn` and `/api/margot/voice` return optional `audio_base64` + `audio_mime_type` when `MARGOT_VOICE_REPLY_ENABLED=1`; MCP `margot_turn` / `margot_voice_turn` expose the same in `structuredContent` for Hermes `sendVoice`.
- **Telegram send:** `swarm/margot_telegram.py` replaces broken `telegram_alerts` path — per-chat `sendMessage` / `sendVoice` via Bot API.
- **Health:** `margot_route` probe prefers Supabase `margot_conversations` over ephemeral JSONL.

## Test plan
- [x] `python -m pytest tests/ -q` → **2428 passed**, 5 skipped, 2 xfailed
- [x] `npx tsc --noEmit` (dashboard)
- [ ] Hermes: enable `MARGOT_VOICE_REPLY_ENABLED=1` on Railway + `ELEVENLABS_API_KEY`; verify MCP `structuredContent.audio_base64` → `sendVoice`
- [ ] Telegram: dispatch `[RESEARCH depth=deep ...]` → next message receives harvested report

## Manual verification path
1. Send Margot a text message via Hermes → reply returns within 120s.
2. Trigger deep research → send another message → async findings appear in reply.
3. Mission Control `/api/health/full` → `margot_route.source` = `supabase` when turns exist.

## Push commands (auth required locally)
```bash
git push -u origin fix/margot-p0-go-live
gh pr create --title "fix(margot): P0 go-live — inflight harvest, voice bridge, Telegram send, health" --body-file .harness/pr-bodies/margot-p0-go-live.md
gh pr merge --squash --delete-branch
```
