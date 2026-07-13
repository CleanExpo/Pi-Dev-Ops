export type BrandSlug = 'dr' | 'nrpg' | 'ra' | 'carsi' | 'ccw' | 'synthex' | 'unite';
export type RemotionChannel = 'linkedin' | 'website' | 'youtube' | 'sales' | 'ads';
export type RemotionRenderMode = 'draft' | 'production';
export type ImageProvider = 'chatgpt' | 'nano-banana-2-pro' | 'none';

export interface RemotionImageAsset {
  sceneId: string;
  path: string;
  alt: string;
  prompt?: string;
  provider?: ImageProvider;
}

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
  imageProvider: ImageProvider;
  imagePrompt?: string;
  imageAssets: RemotionImageAsset[];
}

const BRANDS = new Set<BrandSlug>(['dr', 'nrpg', 'ra', 'carsi', 'ccw', 'synthex', 'unite']);
const CHANNELS = new Set<RemotionChannel>(['linkedin', 'website', 'youtube', 'sales', 'ads']);
const RENDER_MODES = new Set<RemotionRenderMode>(['draft', 'production']);
const IMAGE_PROVIDERS = new Set<ImageProvider>(['chatgpt', 'nano-banana-2-pro', 'none']);

function readString(input: Record<string, unknown>, key: string, minLength: number): string {
  const value = input[key];
  if (typeof value !== 'string' || value.trim().length < minLength) {
    throw new Error(`brief-schema: ${key} must be a string with at least ${minLength} characters`);
  }
  return value.trim();
}

function readOptionalString(input: Record<string, unknown>, key: string): string | undefined {
  const value = input[key];
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value !== 'string') throw new Error(`brief-schema: ${key} must be a string`);
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

function readImageAssets(input: Record<string, unknown>, defaultProvider: ImageProvider): RemotionImageAsset[] {
  const raw = input.imageAssets ?? [];
  if (!Array.isArray(raw)) throw new Error('brief-schema: imageAssets must be an array');
  return raw.map((item, index) => {
    if (typeof item !== 'object' || item === null || Array.isArray(item)) {
      throw new Error(`brief-schema: imageAssets[${index}] must be an object`);
    }
    const asset = item as Record<string, unknown>;
    const provider = asset.provider === undefined
      ? defaultProvider
      : readEnum(asset, 'provider', IMAGE_PROVIDERS, defaultProvider);
    return {
      sceneId: readString(asset, 'sceneId', 2),
      path: readString(asset, 'path', 2).replace(/^\/+/, ''),
      alt: readString(asset, 'alt', 2),
      prompt: readOptionalString(asset, 'prompt'),
      provider,
    };
  });
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
    const imageProvider = readEnum(input, 'imageProvider', IMAGE_PROVIDERS, 'none');
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
      imageProvider,
      imagePrompt: readOptionalString(input, 'imagePrompt'),
      imageAssets: readImageAssets(input, imageProvider),
    };
  },
};
