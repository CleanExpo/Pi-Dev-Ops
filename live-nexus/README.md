# Live Nexus

Client-facing live meeting capture for Unite-Group. The production flow is:

1. Browser starts a meeting at `https://live.unite-group.ink`
2. `/api/session` mints an AssemblyAI v3 streaming token
3. The meeting page streams transcript chunks
4. `/api/synthesize` turns transcript into topics and action items
5. `/api/save` writes the final markdown record to Google Drive

## Local Development

```bash
pnpm install
pnpm dev
```

Open `http://localhost:3000`.

## Verification

Run the local gates before changing deployment behavior:

```bash
pnpm test
pnpm typecheck
pnpm e2e
pnpm build
```

Run the production smoke without writing to Drive:

```bash
pnpm smoke:prod
```

GitHub Actions also runs this no-write smoke every 2 hours via
`Live Nexus Smoke (production)`.

Run the production smoke including `/api/save` only when a Drive smoke file is acceptable:

```bash
pnpm smoke:prod:save
```

Override the target URL with `LIVE_NEXUS_URL=https://...`.

## Production

- Canonical URL: `https://live.unite-group.ink`
- Vercel project: `live-nexus`
- Required production environment:
  - `ASSEMBLYAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `GOOGLE_OAUTH_CLIENT_SECRET`
  - `GOOGLE_OAUTH_REFRESH_TOKEN`
  - `DRIVE_FOLDER_ID`

Keep `/api/save` smoke files clearly named and remove them during Brain folder cleanup.
