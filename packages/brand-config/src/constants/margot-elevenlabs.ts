/**
 * Margot ElevenLabs voice — global SSOT for TypeScript consumers.
 *
 * NOT `ELEVENLABS_VOICE_ID` / `SYNTHEX_ELEVENLABS_VOICE_ID` — those are for
 * other agents. Margot surfaces must use this constant or `resolveMargotVoice()`.
 *
 * Keep in sync with `.harness/margot/assets/margot_identity.json` and
 * `app/server/margot_voice.py`.
 */
export const MARGOT_ELEVENLABS_VOICE_ID = 'p43fx6U8afP2xoq1Ai9f' as const;
