# Margot Generation Substrate Design

**Date:** 2026-07-01
**Owner:** Unite-Group / Pi-Dev-Ops
**Status:** Approved experiment

## Purpose

Create the first code substrate for generating Margot visual assets without prompt drift. The system starts from the accepted canonical Margot avatar in Brain-1 and produces deterministic OpenAI `gpt-image-2` generation payloads for Unite-Group project surfaces.

This is not a RileyJarvis clone and not a desktop companion. It is the asset-generation layer that later Margot UI, voice, media, and cockpit work can consume.

## Evidence

- Brain-1 locks the accepted Margot avatar at `/Users/phill-mac/2nd Brain/2nd Brain/Wiki/assets/margot/margot-canonical-avatar-2026-07-01.png`.
- Brain-1 `Wiki/margot-visual-identity.md` stores the canonical identity, baseline prompt, and brand-safety boundary.
- Pi-Dev-Ops already has Margot text and voice routes through `app/server/routes/margot.py` and MCP tools in `mcp/pi-ceo-server.js`.
- OpenAI's image-generation guide and image reference say the Image API can generate from a text prompt, GPT image models return base64 image data, and `gpt-image-2` supports `1024x1536`.
- OpenAI's image-generation guide recommends the Image API for single-prompt image generation and the Responses API for conversational image workflows.

## Scope

### In

- Versioned Margot identity manifest.
- Project-specific prompt overlays for Unite-Group portfolio projects.
- Deterministic dry-run payload generation.
- Optional live OpenAI Image API call gated by `--live`.
- Local provenance JSON beside every generated asset.
- Tests for manifest validation, prompt safety, payload shape, and output naming.

### Out

- No desktop companion shell.
- No Realtime voice session code.
- No computer-use.
- No dashboard UI.
- No automatic publishing or client delivery.
- No secrets stored or printed.

## Design

The generator has three layers:

1. **Manifest:** `.harness/margot/assets/margot_identity.json` holds the canonical asset path, default OpenAI model settings, allowed project overlays, variant templates, and safety rules.
2. **Prompt builder:** `scripts/margot_generate.py` loads the manifest, combines canonical identity, project overlay, variant template, and user-safe optional notes into one deterministic prompt.
3. **Execution mode:** dry-run prints the payload and provenance preview; live mode posts to `https://api.openai.com/v1/images/generations` with `OPENAI_API_KEY`, decodes `data[0].b64_json`, writes a PNG, and writes provenance JSON.

## Safety

- Dry-run is default.
- Live mode requires `--live`; no accidental spend.
- API key is read from `OPENAI_API_KEY` only and is never printed.
- Live mode requires the canonical asset file to exist locally.
- Prompt includes the brand-safe rule from Brain-1: realistic, professional, non-robotic, no deliberate sexualisation.
- Unknown projects fail closed.
- Project context is curated in the manifest, not free-form client data.

## Acceptance Criteria

- `python scripts/margot_generate.py --project unite-group --variant avatar --dry-run` prints a valid JSON payload.
- `python -m pytest tests/test_margot_asset_generator.py -q` passes.
- The payload uses `model: gpt-image-2`.
- The prompt includes the canonical Margot identity, project overlay, variant direction, and safety boundary.
- No secrets are committed or printed.
- Live mode writes image and provenance files under `.harness/margot/generated-assets/`.

## Verification

```bash
python scripts/margot_generate.py --project unite-group --variant avatar --dry-run
python -m pytest tests/test_margot_asset_generator.py -q
python -m py_compile scripts/margot_generate.py
scripts/secrets_check.py scripts/margot_generate.py tests/test_margot_asset_generator.py .harness/margot/assets/margot_identity.json docs/superpowers/specs/2026-07-01-margot-generation-substrate-design.md
```

## Next Slice

After this generator is green, wire the manifest into a small dashboard/Mission Control preview panel. Realtime voice and computer-use stay separate behind the existing Margot and Hermes gates.
