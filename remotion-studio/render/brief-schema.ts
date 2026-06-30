export type BrandSlug = 'dr' | 'nrpg' | 'ra' | 'carsi' | 'ccw' | 'synthex' | 'unite';
export type RemotionChannel = 'linkedin' | 'website' | 'youtube' | 'sales' | 'ads';
export type RemotionRenderMode = 'draft' | 'production';

export interface RemotionOneShotBrief {
  brand: BrandSlug;
  audience: string;
  channel: RemotionChannel;
  durationSec: number;
  goal: string;
  cta: string;
  voiceProfile: 'synthex_default_single_voice';
  renderMode: RemotionRenderMode;
  brief: string;
}

const BRANDS = new Set<BrandSlug>(['dr', 'nrpg', 'ra', 'carsi', 'ccw', 'synthex', 'unite']);
const CHANNELS = new Set<RemotionChannel>(['linkedin', 'website', 'youtube', 'sales', 'ads']);
const RENDER_MODES = new Set<RemotionRenderMode>(['draft', 'production']);

function readString(input: Record<string, unknown>, key: string, minLength: number): string {
  const value = input[key];
  if (typeof value !== 'string' || value.trim().length < minLength) {
    throw new Error(`brief-schema: ${key} must be a string with at least ${minLength} characters`);
  }
  return value.trim();
}

function readDuration(input: Record<string, unknown>): number {
  const raw = input.durationSec ?? 60;
  const value = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isInteger(value) || value < 15 || value > 180) {
    throw new Error('brief-schema: durationSec must be an integer between 15 and 180');
  }
  return value;
}

function readEnum<T extends string>(
  input: Record<string, unknown>,
  key: string,
  values: Set<T>,
  fallback?: T,
): T {
  const raw = input[key] ?? fallback;
  if (typeof raw !== 'string' || !values.has(raw as T)) {
    throw new Error(`brief-schema: ${key} must be one of ${Array.from(values).join(', ')}`);
  }
  return raw as T;
}

export const remotionOneShotBriefSchema = {
  parse(raw: unknown): RemotionOneShotBrief {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
      throw new Error('brief-schema: brief must be an object');
    }
    const input = raw as Record<string, unknown>;
    const voiceProfile = input.voiceProfile ?? 'synthex_default_single_voice';
    if (voiceProfile !== 'synthex_default_single_voice') {
      throw new Error('brief-schema: voiceProfile must be synthex_default_single_voice');
    }
    return {
      brand: readEnum(input, 'brand', BRANDS),
      audience: readString(input, 'audience', 2),
      channel: readEnum(input, 'channel', CHANNELS, 'linkedin'),
      durationSec: readDuration(input),
      goal: readString(input, 'goal', 5),
      cta: readString(input, 'cta', 2),
      voiceProfile,
      renderMode: readEnum(input, 'renderMode', RENDER_MODES, 'draft'),
      brief: readString(input, 'brief', 5),
    };
  },
};
