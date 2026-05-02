/**
 * ElevenLabs voiceover synthesis.
 *
 * - Reads storyboard scenes that lack a `voiceoverAudioPath`
 * - Synthesises each via ElevenLabs API using the brand's configured voiceId
 * - Writes MP3 files to `<root>/public/audio/<jobId>/scene-<n>.mp3`
 *   (under public/ so staticFile() can resolve them at render time)
 * - Mutates the storyboard scenes in place to add `voiceoverAudioPath`
 *
 * Cache key: sha1(voiceId + style + text). Cache hits skip the API call and reuse the file.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { brands, BrandSlug } from '../src/brands';

export interface Scene {
  sceneId: string;
  durationSec: number;
  voiceover: string;
  onScreenText: string;
  voiceoverAudioPath?: string;
}

export interface Storyboarded {
  brand: string;
  storyboard: Scene[];
}

const ELEVENLABS_API = 'https://api.elevenlabs.io/v1/text-to-speech';

function cacheKey(voiceId: string, style: string, text: string): string {
  return crypto.createHash('sha1').update(`${voiceId}|${style}|${text}`).digest('hex');
}

async function synthesise(text: string, voiceId: string, apiKey: string, outPath: string) {
  // Lazy import so the module loads even when ElevenLabs SDK isn't installed yet.
  const res = await fetch(`${ELEVENLABS_API}/${voiceId}?output_format=mp3_44100_128`, {
    method: 'POST',
    headers: {
      'xi-api-key': apiKey,
      'Content-Type': 'application/json',
      Accept: 'audio/mpeg',
    },
    body: JSON.stringify({
      text,
      model_id: 'eleven_multilingual_v2',
      voice_settings: { stability: 0.5, similarity_boost: 0.75 },
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`ElevenLabs ${res.status}: ${body.slice(0, 200)}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, buf);
}

export async function synthesiseStoryboard(
  props: Storyboarded,
  jobId: string,
  rootDir: string,
): Promise<void> {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  if (!apiKey) {
    console.warn('[voiceover] ELEVENLABS_API_KEY missing — rendering without voiceover');
    return;
  }
  const cfg = brands[props.brand as BrandSlug];
  if (!cfg) throw new Error(`[voiceover] unknown brand ${props.brand}`);

  const cacheDir = path.join(rootDir, 'public', 'audio', '_cache');
  const jobDir = path.join(rootDir, 'public', 'audio', jobId);
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.mkdirSync(jobDir, { recursive: true });

  for (let i = 0; i < props.storyboard.length; i++) {
    const scene = props.storyboard[i];
    if (scene.voiceoverAudioPath || !scene.voiceover) continue;

    const key = cacheKey(cfg.voiceover.elevenLabsVoiceId, cfg.voiceover.style, scene.voiceover);
    const cachePath = path.join(cacheDir, `${key}.mp3`);
    if (!fs.existsSync(cachePath)) {
      console.log(`[voiceover] synthesising scene ${i} (${scene.sceneId}) — ${scene.voiceover.slice(0, 60)}…`);
      await synthesise(scene.voiceover, cfg.voiceover.elevenLabsVoiceId, apiKey, cachePath);
    } else {
      console.log(`[voiceover] cache hit scene ${i} (${scene.sceneId})`);
    }
    const linkPath = path.join(jobDir, `scene-${i}.mp3`);
    fs.copyFileSync(cachePath, linkPath);
    scene.voiceoverAudioPath = path.join('audio', jobId, `scene-${i}.mp3`);
  }
}
