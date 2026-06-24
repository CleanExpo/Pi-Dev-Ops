export interface SingleVoiceConfig {
  provider: 'elevenlabs';
  source: 'Synthex';
  envKey: 'ELEVENLABS_API_KEY';
  voiceIdEnvKey: 'SYNTHEX_ELEVENLABS_VOICE_ID' | 'ELEVENLABS_VOICE_ID';
  voiceId: string;
}

export function resolveSingleVoice(env: NodeJS.ProcessEnv = process.env): SingleVoiceConfig {
  const synthexVoice = env.SYNTHEX_ELEVENLABS_VOICE_ID?.trim();
  const fallbackVoice = env.ELEVENLABS_VOICE_ID?.trim();
  const voiceId = synthexVoice || fallbackVoice || '';
  if (!voiceId) {
    throw new Error(
      'single-voice: missing SYNTHEX_ELEVENLABS_VOICE_ID or ELEVENLABS_VOICE_ID. Use the existing Synthex ElevenLabs voice; do not introduce multiple voices.',
    );
  }
  return {
    provider: 'elevenlabs',
    source: 'Synthex',
    envKey: 'ELEVENLABS_API_KEY',
    voiceIdEnvKey: synthexVoice ? 'SYNTHEX_ELEVENLABS_VOICE_ID' : 'ELEVENLABS_VOICE_ID',
    voiceId,
  };
}

export function assertSingleVoice(sceneVoiceIds: Array<string | undefined>, requiredVoiceId: string): void {
  const unique = new Set(sceneVoiceIds.map((v) => v?.trim()).filter((v): v is string => Boolean(v)));
  unique.add(requiredVoiceId);
  if (unique.size !== 1) {
    throw new Error(
      `single-voice: multiple voices requested (${Array.from(unique).join(', ')}). Remotion production must use exactly one Synthex ElevenLabs voice.`,
    );
  }
}
