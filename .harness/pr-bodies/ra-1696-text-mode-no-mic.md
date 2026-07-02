## Summary

RA-1696 desk voice: `--mode text` for no-mic Mac mini; Pi-CEO Railway fallback when local Hermes chat 500s; `requirements-desk-voice.txt` for deps; API_SERVER_KEY from op run.

## Test plan

- [ ] `python -m pip install -r scripts/requirements-desk-voice.txt`
- [ ] `op run --env-file=~/.hermes/.env -- python scripts/verify_desk_voice_stack.py`
- [ ] `op run --env-file=~/.hermes/.env -- python scripts/desk_voice_loop.py --mode text`
- [ ] Telegram voice note for full E2E (no desk mic)
- [ ] USB headset + `--mode ptt` in Terminal.app (optional)

## Known issue

Local Hermes `:8642` chat returns 500 (`_is_hermes_internal_secret` import) — loop falls back to Pi-CEO; separate Hermes fix tracked on Linear.
