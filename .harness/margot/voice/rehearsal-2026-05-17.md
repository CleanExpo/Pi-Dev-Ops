# Margot Voice v0 Rehearsal

Date: 2026-05-17
Surface: Unite CRM Command Center
Voice shell: ElevenLabs signed URL widget
Decision logic: Pi-CEO/Margot
Status: YELLOW

## Checks

- [x] Pi-CEO backend imports and test route suite passes.
- [x] Unite CRM signed URL route test returns a signed URL without exposing the API key.
- [x] Unite CRM task route test creates `voice_command_sessions` and `tasks` rows through the mocked Supabase client.
- [x] Packet builder classified low-risk CRM task correctly.
- [x] Pi-CEO webhook test creates CRM task handoff and board-specific Kanban card through mocked adapters.
- [x] Fallback packet created when CRM write is unavailable.
- [x] Unite CRM command-center page is protected by login.
- [ ] Live browser click from command center to ElevenLabs widget was not completed in this browser context because `/en/command-center` redirected to `/en/login`.
- [ ] Live production CRM row and live Hermes Kanban card were not created during rehearsal; this stayed local/test-only.

## Evidence

- Pi-CEO test gate: `python -m pytest tests/test_margot_voice_packet.py tests/test_elevenlabs_margot_voice_route.py tests/test_kanban_adapter.py -q` -> 25 passed.
- Pi-CEO import gate: `python -c "from app.server.main import app; print(type(app))"` -> `<class 'fastapi.applications.FastAPI'>`.
- Unite CRM API tests: `npm run test:all -- tests/integration/api/margot-voice-signed-url.test.ts tests/integration/api/margot-voice-task.test.ts --runInBand` -> 6 passed.
- Unite CRM type-check: `npm run type-check -- --pretty false` -> exit 0.
- Unite CRM lint: `npm run lint` -> exit 0 with 485 inherited warnings.
- Strict lint for touched files was run before commits with `--max-warnings=0` and passed.
- Local Pi-CEO server started on `127.0.0.1:7778`; it was stopped after startup because the default environment also enabled background cron/swarm loops.
- Local Unite CRM dev server started on `http://localhost:3002`.
- Browser check: `http://localhost:3002/en/command-center` redirected to `http://localhost:3002/en/login`, proving the command-center surface is auth gated.
- Fallback rehearsal packet:
  - Packet ID: `voice_07317263d968c49f`
  - Route: `unite_crm`
  - Risk: `low`
  - Path: `.harness/margot/voice/voice_07317263d968c49f.json`

## Result

The build is ready for an authenticated CRM browser rehearsal. The production workflow behavior was not changed, and no live ElevenLabs call, live CRM write, live Kanban write, deployment, or publish action was executed.
