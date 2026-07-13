# Remotion One-Shot Video Command Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a production-grade `/remotion-video` one-shot command and specialised Remotion skill set that can create scalable marketing videos with correct timing, sync, voice pacing, visual professionalism, editing direction, and integration discipline across Hermes, Claude, Synthex, and Unite-Group.

**Architecture:** Add a thin command/router layer that turns a marketing brief into a deterministic Remotion production packet, then renders through the existing `remotion-studio` pipeline. Keep the current Remotion stack, harden it with preflight/script/audio/image/timing gates, and expose the workflow through small specialised skills instead of one giant skill. Use the existing Synthex ElevenLabs credentials and enforce a single configured voice for every render.

**Tech Stack:** Pi-Dev-Ops skills registry, `src/tao/skills.py` intent routing, `agentskills.json`/`agentskills.yaml`, Remotion 4, TypeScript, React 19, ElevenLabs TTS, ffprobe/ffmpeg, existing `remotion-studio/render/*`, Claude command markdown, Hermes skills.

---

## Current context / assumptions

- Active repo: `/Users/phillmcgurk/Pi-Dev-Ops`.
- Existing Remotion app: `/Users/phillmcgurk/Pi-Dev-Ops/remotion-studio`.
- Existing render entrypoint: `/Users/phillmcgurk/Pi-Dev-Ops/remotion-studio/render/render.ts`.
- Existing voice synthesis: `/Users/phillmcgurk/Pi-Dev-Ops/remotion-studio/render/voiceover.ts`.
- Existing timing guards:
  - `/Users/phillmcgurk/Pi-Dev-Ops/remotion-studio/render/audio-fit.ts`
  - `/Users/phillmcgurk/Pi-Dev-Ops/remotion-studio/render/validate.ts`
- Existing README claims Remotion skills should live at `Pi-Dev-Ops/skills/remotion-*`, but no `skills/remotion-*` files currently exist.
- Existing command/intent routing lives in `/Users/phillmcgurk/Pi-Dev-Ops/src/tao/skills.py`.
- This should be made available to both Hermes and Claude:
  - Hermes: via skill(s) and Pi-Dev-Ops intent routing; optionally copied/installed to `~/.hermes/skills` after repo version is reviewed.
  - Claude: via repo-local command markdown, likely `.claude/commands/remotion-video.md` if the repo accepts that convention.
- This should work for Synthex and Unite-Group without adding a new vendor.
- ElevenLabs keys already exist in Synthex and may be reused for this project.
- Hard requirement from Phill: one voice only. No multi-voice casts, no per-brand voice switching, no mixed narrator voices.
- New vendor policy: no new external accounts/services. Use existing ElevenLabs, Remotion, GitHub, Vercel/Railway/etc. only.

---

## Proposed command model

Use one public command:

```text
/remotion-video <brief>
```

The command should produce a one-shot video pipeline:

1. Parse brief into a production packet.
2. Select brand/audience/channel/duration.
3. Produce script + storyboard + scene timings.
4. Enforce one voice profile.
5. Generate/check voiceover audio.
6. Auto-fit scene durations to actual audio.
7. Render video.
8. Probe final MP4 for audio/video drift and silent render failure.
9. Produce delivery packet with output path, evidence, and next action.

Preferred initial alias names:

```text
/remotion-video
/remotion-one-shot
/video
```

Implementation should start with `remotion-video` intent in Pi-Dev-Ops, not with real Hermes core slash-command changes. After proving the repo command, promote the same wrapper to Hermes/Claude surfaces.

---

## Specialised skills to create

Create a composable Remotion skill family under `skills/remotion-*`:

1. `skills/remotion-orchestrator/SKILL.md`
   - Main `/remotion-video` router.
   - Chooses required subskills.
   - Removes noise and turns the brief into one production path.

2. `skills/remotion-production/SKILL.md`
   - Production readiness, render gates, output conventions, artifact policy.
   - Owns render evidence and final pass/fail criteria.

3. `skills/remotion-script/SKILL.md`
   - Turns marketing brief into scene script.
   - Enforces words-per-second budgets and one-voice narration style.

4. `skills/remotion-direction/SKILL.md`
   - Creative direction: hook, pacing, CTA, scene rhythm, shot/scene intent.
   - Prevents generic slide decks.

5. `skills/remotion-editing/SKILL.md`
   - Timing, cuts, transitions, captions, pacing, audio-fit, scene duration discipline.
   - Addresses current sync/timing/render correctness issues.

6. `skills/remotion-integrations/SKILL.md`
   - ElevenLabs, Cloudinary/Vercel/static output, brand-config, Synthex/Unite-Group integration points.
   - Explicitly no new vendors.

7. `skills/remotion-professionalism/SKILL.md`
   - QA rubric for visual quality, brand consistency, motion restraint, typography, legibility, CTA quality.

Keep each `SKILL.md` short. Put long implementation detail into:

```text
skills/remotion-orchestrator/references/one-shot-command-contract.md
skills/remotion-production/references/render-gates.md
skills/remotion-script/references/script-timing-budget.md
skills/remotion-integrations/references/elevenlabs-single-voice.md
```

---

## Command contract

`/remotion-video` should accept a brief like:

```text
/remotion-video brand=synthex audience=founders channel=linkedin duration=60s goal="explain the agentic marketing engine"
```

Minimum inferred fields:

```json
{
  "brand": "synthex | unite | ccw | ra | dr | nrpg | carsi",
  "audience": "target persona",
  "channel": "linkedin | website | youtube | sales | ads",
  "durationSec": 30,
  "goal": "single business outcome",
  "cta": "single CTA",
  "voiceProfile": "synthex_default_single_voice",
  "style": "professional marketing video",
  "renderMode": "draft | production"
}
```

Hard validation:

- `voiceProfile` must resolve to exactly one configured voice ID.
- No scene may request a different voice.
- Total narration speed target should be approximately 145-160 WPM, defaulting to the repo’s current conservative `2.6 words/sec` budget.
- Scene duration must be extended to fit actual audio, never shortened to clip speech.
- Final MP4 must contain audio unless explicitly `--skipTts=true` and marked draft/silent.
- Audio duration must not exceed video duration beyond tolerance.
- Generated MP4s >1MB must not be committed to git.

---

## Files likely to change

### Pi-Dev-Ops skill and routing files

- Create: `skills/remotion-orchestrator/SKILL.md`
- Create: `skills/remotion-production/SKILL.md`
- Create: `skills/remotion-script/SKILL.md`
- Create: `skills/remotion-direction/SKILL.md`
- Create: `skills/remotion-editing/SKILL.md`
- Create: `skills/remotion-integrations/SKILL.md`
- Create: `skills/remotion-professionalism/SKILL.md`
- Modify: `src/tao/skills.py`
- Regenerate: `agentskills.json`
- Regenerate: `agentskills.yaml`

### Tests

- Create: `tests/test_remotion_video_command_skill.py`
- Create or extend: `tests/test_remotion_single_voice_contract.py`

### Remotion one-shot command implementation

- Create: `remotion-studio/render/one-shot.ts`
- Create: `remotion-studio/render/brief-schema.ts`
- Create: `remotion-studio/render/single-voice.ts`
- Create: `remotion-studio/render/script-budget.ts` if existing `validate.ts` should not grow.
- Modify: `remotion-studio/render/voiceover.ts`
- Modify: `remotion-studio/render/render.ts` only if reusable flags are needed.
- Modify: `remotion-studio/README.md` to document `/remotion-video` and one-voice policy.

### Claude command surface

- Create: `.claude/commands/remotion-video.md`
- Optional aliases after review:
  - `.claude/commands/remotion-one-shot.md`
  - `.claude/commands/video.md`

### Hermes surface

Initial repo-level delivery:

- Add skill to Pi-Dev-Ops skills registry and `agentskills.*`.

Follow-up after review:

- Create or install user-local Hermes skill mirroring `remotion-orchestrator`, or add a documented copy step:
  - source: `Pi-Dev-Ops/skills/remotion-orchestrator/SKILL.md`
  - target: `~/.hermes/skills/media/remotion-video/SKILL.md`

Do not modify another Hermes profile without explicit approval.

### Synthex / Unite-Group availability

Plan for cross-project availability through repo paths first:

- Pi-Dev-Ops owns canonical skill implementation.
- Synthex consumes via existing credentials and command docs.
- Unite-Group consumes via repo skill routing and brand-config entries.

If Synthex and Unite-Group have separate repos/Claude command roots, inspect them in the implementation phase and add thin command docs that point back to the Pi-Dev-Ops canonical command.

---

## Step-by-step plan

### Task 1: Add RED tests for Remotion command skill loading

**Objective:** Prove that the Remotion command does not exist yet and define the expected routing contract.

**Files:**
- Create: `tests/test_remotion_video_command_skill.py`
- Modify later: `src/tao/skills.py`
- Create later: `skills/remotion-orchestrator/SKILL.md`

**Step 1: Write failing test**

```python
from __future__ import annotations

from src.tao import skills


def test_remotion_orchestrator_skill_loads_command_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("remotion-orchestrator")

    assert skill is not None
    assert "/remotion-video" in skill["description"]
    assert "one-shot" in skill["body"]
    assert "single voice" in skill["body"]
    assert "ElevenLabs" in skill["body"]
    assert "no new vendors" in skill["body"]


def test_video_intent_routes_to_remotion_skill_family_first():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("video")]

    assert routed[:3] == [
        "remotion-orchestrator",
        "remotion-script",
        "remotion-production",
    ]
    assert "remotion-editing" in routed
    assert "remotion-integrations" in routed
    assert "remotion-professionalism" in routed
```

**Step 2: Run test to verify failure**

Run:

```bash
python3 -m pytest tests/test_remotion_video_command_skill.py -q
```

Expected: FAIL because `remotion-orchestrator` and `video` intent route do not exist yet.

**Step 3: Commit?**

Do not commit failing tests alone unless working in a long PR stack. Prefer implement next task immediately, then commit green.

---

### Task 2: Create the Remotion skill family

**Objective:** Add the specialised skills that encode production, script, integration, professionalism, editing, and direction responsibilities.

**Files:**
- Create: `skills/remotion-orchestrator/SKILL.md`
- Create: `skills/remotion-production/SKILL.md`
- Create: `skills/remotion-script/SKILL.md`
- Create: `skills/remotion-direction/SKILL.md`
- Create: `skills/remotion-editing/SKILL.md`
- Create: `skills/remotion-integrations/SKILL.md`
- Create: `skills/remotion-professionalism/SKILL.md`

**Step 1: Create `skills/remotion-orchestrator/SKILL.md`**

Required frontmatter shape:

```yaml
---
name: remotion-orchestrator
description: /remotion-video one-shot Remotion command skill. Use when the operator asks for a marketing, explainer, social, product, or launch video and needs one governed Remotion production path with script, direction, editing, integrations, professionalism, timing, voice, and render gates.
owner_role: Producer
status: remotion-wave-1
intents: video, remotion-video, remotion-one-shot, marketing-video
---
```

Minimum body requirements:

- Define `/remotion-video` as one-shot command.
- State it is the router, not a replacement for subskills.
- Enforce the single voice rule.
- State use existing Synthex ElevenLabs credentials.
- State no new vendors/accounts.
- State output packet path: `.harness/remotion/<jobId>/production-packet.json`.
- State final render report path: `.harness/remotion/<jobId>/render-report.md`.

**Step 2: Create each subskill**

Each subskill should have:

- Short `description` with precise trigger.
- `automation: manual` only if it should not auto-load. For command path, leave auto if routed.
- Clear boundaries.
- Verification checklist.

**Step 3: Run skill loader smoke**

Run:

```bash
python3 - <<'PY'
from src.tao import skills
skills.invalidate_cache()
for name in [
    "remotion-orchestrator",
    "remotion-production",
    "remotion-script",
    "remotion-direction",
    "remotion-editing",
    "remotion-integrations",
    "remotion-professionalism",
]:
    assert skills.get_skill(name), name
print("ok")
PY
```

Expected: `ok`.

---

### Task 3: Wire `video` and `/remotion-video` routing

**Objective:** Make the Remotion command family available through Pi-Dev-Ops intent routing.

**Files:**
- Modify: `src/tao/skills.py`
- Test: `tests/test_remotion_video_command_skill.py`

**Step 1: Patch `_INTENT_SKILLS`**

Add:

```python
    "video": [
        "remotion-orchestrator",
        "remotion-script",
        "remotion-production",
        "remotion-direction",
        "remotion-editing",
        "remotion-integrations",
        "remotion-professionalism",
    ],
    "remotion-video": [
        "remotion-orchestrator",
        "remotion-script",
        "remotion-production",
        "remotion-direction",
        "remotion-editing",
        "remotion-integrations",
        "remotion-professionalism",
    ],
```

**Step 2: Run focused test**

Run:

```bash
python3 -m pytest tests/test_remotion_video_command_skill.py -q
```

Expected: PASS.

**Step 3: Commit**

```bash
git add src/tao/skills.py skills/remotion-* tests/test_remotion_video_command_skill.py
git commit -m "feat(skills): add remotion video command routing"
```

---

### Task 4: Add single-voice contract tests

**Objective:** Prevent the current and future pipelines from using more than one voice.

**Files:**
- Create: `tests/test_remotion_single_voice_contract.py`
- Create later: `remotion-studio/render/single-voice.ts`

**Step 1: Write failing test**

Use Python to inspect text files without running Node if simpler:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_single_voice_module_exists_and_names_synthex_source():
    text = (ROOT / "remotion-studio" / "render" / "single-voice.ts").read_text()

    assert "Synthex" in text
    assert "ELEVENLABS" in text
    assert "assertSingleVoice" in text
    assert "multiple voices" in text.lower()


def test_remotion_skills_document_single_voice_policy():
    for rel in [
        "skills/remotion-orchestrator/SKILL.md",
        "skills/remotion-integrations/SKILL.md",
        "skills/remotion-script/SKILL.md",
    ]:
        text = (ROOT / rel).read_text()
        assert "single voice" in text.lower(), rel
        assert "ElevenLabs" in text, rel
```

**Step 2: Run to verify failure**

```bash
python3 -m pytest tests/test_remotion_single_voice_contract.py -q
```

Expected: FAIL until `single-voice.ts` exists.

---

### Task 5: Implement single voice resolver

**Objective:** Add a deterministic module that resolves exactly one ElevenLabs voice and rejects mixed voices.

**Files:**
- Create: `remotion-studio/render/single-voice.ts`
- Modify: `remotion-studio/render/voiceover.ts`
- Test: `tests/test_remotion_single_voice_contract.py`

**Step 1: Create `single-voice.ts`**

Core implementation:

```ts
export interface SingleVoiceConfig {
  provider: 'elevenlabs';
  source: 'Synthex';
  envKey: 'ELEVENLABS_API_KEY';
  voiceIdEnvKey: 'SYNTHEX_ELEVENLABS_VOICE_ID' | 'ELEVENLABS_VOICE_ID';
  voiceId: string;
}

export function resolveSingleVoice(env: NodeJS.ProcessEnv = process.env): SingleVoiceConfig {
  const voiceId = env.SYNTHEX_ELEVENLABS_VOICE_ID || env.ELEVENLABS_VOICE_ID || '';
  if (!voiceId.trim()) {
    throw new Error(
      'single-voice: missing SYNTHEX_ELEVENLABS_VOICE_ID or ELEVENLABS_VOICE_ID. Use the existing Synthex ElevenLabs voice; do not introduce multiple voices.',
    );
  }
  return {
    provider: 'elevenlabs',
    source: 'Synthex',
    envKey: 'ELEVENLABS_API_KEY',
    voiceIdEnvKey: env.SYNTHEX_ELEVENLABS_VOICE_ID ? 'SYNTHEX_ELEVENLABS_VOICE_ID' : 'ELEVENLABS_VOICE_ID',
    voiceId,
  };
}

export function assertSingleVoice(sceneVoiceIds: Array<string | undefined>, requiredVoiceId: string): void {
  const unique = new Set(sceneVoiceIds.filter(Boolean));
  unique.add(requiredVoiceId);
  if (unique.size !== 1) {
    throw new Error(
      `single-voice: multiple voices requested (${Array.from(unique).join(', ')}). Remotion production must use exactly one Synthex ElevenLabs voice.`,
    );
  }
}
```

**Step 2: Modify `voiceover.ts`**

Change voice resolution so it uses `resolveSingleVoice()` instead of per-brand voice IDs by default.

Likely patch:

```ts
import { resolveSingleVoice, assertSingleVoice } from './single-voice';
```

Inside `synthesiseStoryboard`:

```ts
const singleVoice = resolveSingleVoice(process.env);
assertSingleVoice(
  props.storyboard.map((scene) => (scene as { voiceId?: string }).voiceId),
  singleVoice.voiceId,
);

// Use singleVoice.voiceId instead of cfg.voiceover.elevenLabsVoiceId.
const key = cacheKey(singleVoice.voiceId, cfg.voiceover.style, scene.voiceover);
await synthesise(scene.voiceover, singleVoice.voiceId, apiKey, cachePath);
```

Do not log or print API keys.

**Step 3: Run tests**

```bash
python3 -m pytest tests/test_remotion_single_voice_contract.py -q
```

Expected: PASS.

**Step 4: Typecheck Remotion**

```bash
cd remotion-studio
npm run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add remotion-studio/render/single-voice.ts remotion-studio/render/voiceover.ts tests/test_remotion_single_voice_contract.py
git commit -m "feat(remotion): enforce single ElevenLabs voice"
```

---

### Task 6: Add one-shot brief schema

**Objective:** Convert noisy marketing requests into a typed Remotion production packet.

**Files:**
- Create: `remotion-studio/render/brief-schema.ts`
- Create or extend: `tests/test_remotion_one_shot_schema.py`

**Step 1: Write failing test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_one_shot_brief_schema_defines_required_fields():
    text = (ROOT / "remotion-studio" / "render" / "brief-schema.ts").read_text()
    for token in [
        "brand",
        "audience",
        "channel",
        "durationSec",
        "goal",
        "cta",
        "voiceProfile",
        "renderMode",
        "RemotionOneShotBrief",
    ]:
        assert token in text
```

**Step 2: Create `brief-schema.ts`**

Use `zod` since the Remotion app already depends on it:

```ts
import { z } from 'zod';

export const remotionOneShotBriefSchema = z.object({
  brand: z.enum(['dr', 'nrpg', 'ra', 'carsi', 'ccw', 'synthex', 'unite']),
  audience: z.string().min(2),
  channel: z.enum(['linkedin', 'website', 'youtube', 'sales', 'ads']).default('linkedin'),
  durationSec: z.number().int().min(15).max(180).default(60),
  goal: z.string().min(5),
  cta: z.string().min(2),
  voiceProfile: z.literal('synthex_default_single_voice').default('synthex_default_single_voice'),
  renderMode: z.enum(['draft', 'production']).default('draft'),
  brief: z.string().min(5),
});

export type RemotionOneShotBrief = z.infer<typeof remotionOneShotBriefSchema>;
```

**Step 3: Run tests and typecheck**

```bash
python3 -m pytest tests/test_remotion_one_shot_schema.py -q
cd remotion-studio && npm run typecheck
```

Expected: PASS.

---

### Task 7: Add one-shot production packet generator

**Objective:** Generate script/storyboard/props from a validated brief without rendering yet.

**Files:**
- Create: `remotion-studio/render/one-shot.ts`
- Modify only if needed: `remotion-studio/render/render.ts`
- Test: `tests/test_remotion_one_shot_schema.py`

**Step 1: Implement CLI shape**

`one-shot.ts` should support:

```bash
npx tsx render/one-shot.ts \
  --brief='{"brand":"synthex","audience":"founders","channel":"linkedin","durationSec":60,"goal":"explain agentic marketing","cta":"Book a strategy call","brief":"..."}' \
  --jobId=synthex-founders-$(date +%s) \
  --dryRun=true
```

**Step 2: Generate packet**

Output structure:

```text
.harness/remotion/<jobId>/production-packet.json
.harness/remotion/<jobId>/script.md
.harness/remotion/<jobId>/render-command.sh
```

Packet should include:

```json
{
  "jobId": "...",
  "brief": {},
  "composition": "Explainer",
  "props": {
    "brand": "synthex",
    "hookSec": 8,
    "ctaSec": 8,
    "storyboard": []
  },
  "voicePolicy": {
    "provider": "elevenlabs",
    "source": "Synthex",
    "voiceCount": 1
  },
  "renderCommand": "npm run render -- ..."
}
```

**Step 3: Script/storyboard generation v1**

Do not call an LLM inside this script yet. Keep it deterministic:

- Scene 1: hook, 8 sec.
- Scene 2: problem, 12 sec.
- Scene 3: mechanism, 16 sec.
- Scene 4: proof/benefit, 16 sec.
- Scene 5: CTA, 8 sec.

Each scene gets:

- `sceneId`
- `sceneType`
- `durationSec`
- `voiceover`
- `onScreenText`
- `data.eyebrow` or `data.keypoints`

**Step 4: Run dry-run packet generation**

```bash
cd remotion-studio
npx tsx render/one-shot.ts \
  --brief='{"brand":"synthex","audience":"founders","channel":"linkedin","durationSec":60,"goal":"explain agentic marketing","cta":"Book a strategy call","brief":"Synthex turns marketing ideas into shipped campaigns using agents."}' \
  --jobId=test-synthex-one-shot \
  --dryRun=true
```

Expected:

- Packet files created under `remotion-studio/.harness/remotion/test-synthex-one-shot/` or repo root `.harness/remotion/test-synthex-one-shot/`.
- No MP4 render yet.
- No ElevenLabs API call in dry run.

**Step 5: Commit**

```bash
git add remotion-studio/render/one-shot.ts remotion-studio/render/brief-schema.ts tests/test_remotion_one_shot_schema.py
git commit -m "feat(remotion): add one-shot production packet generator"
```

---

### Task 8: Add render preflight and postrender report for one-shot command

**Objective:** Ensure the command catches sync, timing, silent render, and voice pacing failures before calling output done.

**Files:**
- Modify: `remotion-studio/render/one-shot.ts`
- Reuse: `remotion-studio/render/validate.ts`
- Reuse: `remotion-studio/render/audio-fit.ts`
- Create or extend: `tests/test_remotion_one_shot_schema.py`

**Step 1: Add dry-run validation report**

For dry run, write:

```text
.harness/remotion/<jobId>/preflight-report.md
```

Include:

- target duration
- estimated words/sec per scene
- whether each scene fits
- selected single voice source, without exposing voice ID if considered secret
- expected render command

**Step 2: Add production mode render call**

For `--dryRun=false`, call existing `render/render.ts` or import its logic. Prefer shelling out initially to avoid entangling render code:

```ts
const args = [
  'tsx',
  'render/render.ts',
  `--comp=${packet.composition}`,
  `--out=${outPath}`,
  `--jobId=${jobId}`,
  `--props=${JSON.stringify(packet.props)}`,
];
```

**Step 3: Ensure reports survive failure**

If render fails, still write:

```text
.harness/remotion/<jobId>/render-report.md
```

With status `FAILED` and error excerpt.

**Step 4: Run dry-run test only**

Do not spend ElevenLabs credits in CI. Use `--dryRun=true` and `--skipTts=true` for automated tests.

---

### Task 9: Add Claude command file

**Objective:** Make `/remotion-video` available as a Claude command in the repo.

**Files:**
- Create: `.claude/commands/remotion-video.md`

**Step 1: Create command doc**

Content should instruct Claude to:

- Load Remotion skill family.
- Use `remotion-studio/render/one-shot.ts`.
- Use existing Synthex ElevenLabs credentials only.
- Enforce one voice only.
- Start with dry run unless operator says production render.
- Never create new vendor accounts.
- Never commit MP4 outputs.

Suggested file:

```md
# /remotion-video

Create a one-shot Remotion marketing video production packet or render.

## Required behavior

1. Load the Remotion specialised skill family.
2. Parse the user brief into a one-shot brief.
3. Enforce exactly one ElevenLabs voice: the existing Synthex voice.
4. Run dry-run packet generation first unless the operator explicitly asks for production render.
5. Run typecheck and render validation before reporting done.
6. Do not create new vendor accounts or use more than one voice.
7. Do not commit generated MP4s.

## Command

```bash
cd remotion-studio
npx tsx render/one-shot.ts --brief='<json>' --jobId='<slug>' --dryRun=true
```
```

**Step 2: Add test**

Extend `tests/test_remotion_video_command_skill.py`:

```python
def test_claude_remotion_video_command_exists():
    text = Path(".claude/commands/remotion-video.md").read_text()
    assert "/remotion-video" in text
    assert "single" in text.lower()
    assert "Synthex" in text
```

**Step 3: Run focused tests**

```bash
python3 -m pytest tests/test_remotion_video_command_skill.py -q
```

Expected: PASS.

---

### Task 10: Add Hermes availability plan or local skill promotion script

**Objective:** Make the command available in Hermes without silently modifying other profiles.

**Files:**
- Create: `scripts/install_remotion_hermes_skill.py` or document manual install.
- Optional create after approval: `~/.hermes/skills/media/remotion-video/SKILL.md` using `skill_manage`, but only if Phill explicitly wants local Hermes install now.

**Preferred safe implementation:** Add a repo script that copies canonical skill into active Hermes profile when run by operator.

```python
#!/usr/bin/env python3
from pathlib import Path
import shutil

repo = Path(__file__).resolve().parents[1]
src = repo / "skills" / "remotion-orchestrator" / "SKILL.md"
dst = Path.home() / ".hermes" / "skills" / "media" / "remotion-video" / "SKILL.md"
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dst)
print(f"installed {dst}")
```

Do not run it in the implementation PR unless explicitly approved, because it mutates user-local Hermes state outside the repo.

---

### Task 11: Regenerate manifest

**Objective:** Ensure agentskills registry includes the Remotion skill family.

**Files:**
- Modify: `agentskills.json`
- Modify: `agentskills.yaml`

**Step 1: Run manifest generator**

```bash
python3 -m swarm.agentskills_manifest
```

Expected:

- Skill count increases by at least 7.
- Manifest contains `remotion-orchestrator`.

**Step 2: Verify manifest**

```bash
python3 - <<'PY'
import json
m=json.load(open('agentskills.json'))
ids={s['id'] for s in m.get('skills', [])}
for name in ['remotion-orchestrator','remotion-script','remotion-production','remotion-editing','remotion-integrations','remotion-professionalism','remotion-direction']:
    assert name in ids, name
print('ok')
PY
```

Expected: `ok`.

---

### Task 12: Full local verification

**Objective:** Prove the command is safe, typed, and routeable without spending TTS credits.

Run:

```bash
python3 -m pytest \
  tests/test_remotion_video_command_skill.py \
  tests/test_remotion_single_voice_contract.py \
  tests/test_remotion_one_shot_schema.py \
  tests/test_northstar_shipit_skill.py \
  tests/test_review_command_skill.py \
  -q
```

Expected: all pass.

Run:

```bash
python3 -m py_compile \
  src/tao/skills.py \
  tests/test_remotion_video_command_skill.py \
  tests/test_remotion_single_voice_contract.py \
  tests/test_remotion_one_shot_schema.py
```

Expected: no output, exit 0.

Run:

```bash
cd remotion-studio
npm run typecheck
```

Expected: PASS.

Run dry-run command:

```bash
cd remotion-studio
npx tsx render/one-shot.ts \
  --brief='{"brand":"synthex","audience":"founders","channel":"linkedin","durationSec":60,"goal":"explain agentic marketing","cta":"Book a strategy call","brief":"Synthex turns marketing ideas into shipped campaigns using agents."}' \
  --jobId=test-synthex-one-shot \
  --dryRun=true
```

Expected:

- production packet written
- script written
- render command written
- no MP4 committed
- no API key printed
- no ElevenLabs call in dry run

Run hygiene:

```bash
git diff --check
git diff -- . ':!agentskills.json' ':!agentskills.yaml' | grep -E '^\+.*(api_key|secret|password|token|passwd|Bearer |postgres://|sk-)' -i || true
```

Expected: no findings.

---

### Task 13: PR and merge workflow

**Objective:** Ship through the normal reviewed PR path.

**Step 1: Create branch**

```bash
git checkout main
git pull --ff-only origin main
git checkout -b feature/remotion-one-shot-video-command
```

**Step 2: Commit in logical chunks**

Recommended commits:

```bash
git commit -m "feat(skills): add remotion command skill family"
git commit -m "feat(remotion): enforce single ElevenLabs voice"
git commit -m "feat(remotion): add one-shot production packet generator"
git commit -m "docs(remotion): add claude command for one-shot videos"
```

**Step 3: Push and PR**

```bash
git push -u origin HEAD
gh pr create --base main --head feature/remotion-one-shot-video-command --title "feat(remotion): add one-shot video command" --body-file /tmp/remotion-pr.md
```

**Step 4: Monitor checks**

```bash
for i in $(seq 1 20); do
  gh pr checks <PR_NUMBER> || true
  pending=$(gh pr checks <PR_NUMBER> 2>&1 | grep -cE 'pending|in_progress|queued|waiting')
  [ "$pending" = "0" ] && break
  sleep 30
done
```

**Step 5: Merge if green and policy allows**

Only merge if:

- CI passes.
- Secrets scan passes.
- Typecheck passes.
- CodeRabbit/review checks pass.
- No branch protection/review gate blocks.

Then:

```bash
gh pr merge <PR_NUMBER> --squash --delete-branch
git fetch origin main
git checkout main
git pull --ff-only origin main
```

---

## Production render policy

Start with dry-run only in CI and PR.

Production render requires explicit operator go because it may:

- spend ElevenLabs credits
- take render time
- create large MP4 artifacts
- require real brand/marketing approval

When explicitly approved, run:

```bash
cd remotion-studio
SYNTHEX_ELEVENLABS_VOICE_ID=<already configured in env> \
ELEVENLABS_API_KEY=<already configured in env> \
npx tsx render/one-shot.ts \
  --brief='<validated-json>' \
  --jobId='<job-id>' \
  --dryRun=false
```

Never print either key. Prefer env already loaded from Synthex/1Password/operator shell.

---

## Risks / tradeoffs

1. **Actual Hermes slash command vs repo intent command**
   - True Hermes slash commands require modifying Hermes core `hermes_cli/commands.py` and `cli.py` in the Hermes source repo.
   - Safer first step is a Pi-Dev-Ops `/remotion-video` command skill and Claude command file.
   - Promote to real Hermes command only after the workflow proves stable.

2. **Synthex credential access**
   - The plan assumes existing ElevenLabs keys can be loaded by the shell or Synthex environment.
   - Do not copy, print, or commit keys.
   - Implementation should only reference env names.

3. **One voice vs brand voices**
   - Existing `voiceover.ts` uses brand voice config.
   - New requirement overrides that for this command: one Synthex voice only.
   - If brand-specific videos need different voices later, that must be a separate approved mode, not default.

4. **Image generation sync**
   - The first slice should not introduce image generation API calls.
   - Use existing brand/design systems and code-generated visuals first.
   - Add image generation only after the timing/audio/render command is stable.

5. **MP4 artifact bloat**
   - Generated videos should be gitignored and stored in output/CDN paths.
   - PR should commit code, skill docs, dry-run packets if small, not video files.

6. **Professionalism quality**
   - A successful render is not necessarily a good marketing video.
   - `remotion-professionalism` must include a review rubric for legibility, CTA, pacing, brand, typography, and no generic slide-deck look.

---

## Open questions for implementation phase

These should not block the first dry-run PR, but must be resolved before production rendering:

1. What exact Synthex voice env var should be canonical?
   - Proposed: `SYNTHEX_ELEVENLABS_VOICE_ID`, fallback `ELEVENLABS_VOICE_ID`.

2. Which projects need direct command files?
   - Pi-Dev-Ops definitely.
   - Need inspect for Synthex and Unite-Group Claude command directories before adding there.

3. What should be the primary initial channel?
   - Proposed default: LinkedIn 60s landscape or square.

4. What is the default visual composition?
   - Proposed: existing `Explainer` first, then add a dedicated `MarketingOneShot` composition if output quality is insufficient.

5. Should final renders upload anywhere automatically?
   - Proposed v1: no. Render locally and produce report.
   - Upload/CDN is a separate operator-approved step.

---

## Acceptance criteria

- `/remotion-video` command documented for Claude.
- `video` and `remotion-video` intents route to the Remotion skill family.
- Remotion skill family exists and is included in `agentskills.json` / `agentskills.yaml`.
- One voice only is enforced in code and skill docs.
- Existing Synthex ElevenLabs env is referenced without exposing secrets.
- One-shot dry run produces a production packet from a brief.
- Dry run does not call ElevenLabs and does not render MP4.
- Production mode, when explicitly run, validates audio/video sync and rejects broken/silent renders.
- Local focused tests pass.
- Remotion `npm run typecheck` passes.
- PR checks pass and branch merges cleanly to main.
