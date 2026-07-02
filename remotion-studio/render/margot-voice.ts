import { MARGOT_ELEVENLABS_VOICE_ID } from '@unite-group/brand-config';

export interface MargotVoiceConfig {
  provider: 'elevenlabs';
  source: 'Margot';
  envKey: 'ELEVENLABS_API_KEY';
  voiceIdEnvKey: 'MARGOT_ELEVENLABS_VOICE_ID' | 'MARGOT_VOICE_ID';
  voiceId: string;
}

/** Resolve Margot's locked ElevenLabs voice for Remotion / video renders. */
export function resolveMargotVoice(env: NodeJS.ProcessEnv = process.env): MargotVoiceConfig {
  const override =
    env.MARGOT_ELEVENLABS_VOICE_ID?.trim() || env.MARGOT_VOICE_ID?.trim() || '';
  const voiceId = override || MARGOT_ELEVENLABS_VOICE_ID;
  return {
    provider: 'elevenlabs',
    source: 'Margot',
    envKey: 'ELEVENLABS_API_KEY',
    voiceIdEnvKey: env.MARGOT_ELEVENLABS_VOICE_ID?.trim()
      ? 'MARGOT_ELEVENLABS_VOICE_ID'
      : 'MARGOT_VOICE_ID',
    voiceId,
  };
}

export { MARGOT_ELEVENLABS_VOICE_ID };
