# /remotion-video

Create a one-shot Remotion marketing video production packet or render.

## Required behavior

1. Load the Remotion specialised skill family:
   - `remotion-orchestrator`
   - `remotion-script`
   - `remotion-production`
   - `remotion-direction`
   - `remotion-editing`
   - `remotion-integrations`
   - `remotion-professionalism`
2. Parse the user brief into a one-shot brief.
3. Enforce exactly one single ElevenLabs voice: the existing Synthex voice.
4. Run dry-run packet generation first unless the operator explicitly asks for production render.
5. Run typecheck and render validation before reporting done.
6. Do not create new vendor accounts or use more than one voice.
7. Do not commit generated MP4s.

## Dry-run command

```bash
cd remotion-studio
npx tsx render/one-shot.ts --brief='<json>' --jobId='<slug>' --dryRun=true
```

## Production command

Only after explicit operator approval:

```bash
cd remotion-studio
npx tsx render/one-shot.ts --brief='<json>' --jobId='<slug>' --dryRun=false
```

Never print or persist ElevenLabs keys. Use the existing Synthex environment.
