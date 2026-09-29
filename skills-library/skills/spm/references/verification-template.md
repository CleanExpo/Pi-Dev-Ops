# SPM Verification Template

Use this inside `/spm` to define proof before implementation begins.

## Static checks

```bash
git diff --check
```

## Backend

```bash
python -c "from app.server.main import app"
python -m pytest tests/ -x -q
```

## Dashboard

```bash
cd dashboard
npx tsc --noEmit
npm run build
```

## Smoke

```bash
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD
```

## Browser/UI

Use Playwright, browser MCP, or the repo's existing browser verification method when relevant.

Minimum browser proof for UI work:

- Screenshot desktop
- Screenshot mobile
- Click primary CTAs
- Test empty state
- Test error state
- Test form validation if forms exist
- Test recovery path

## Security

Minimum security review:

- Auth boundary checked
- Permission boundary checked
- No secrets committed
- No unsafe external call added
- Prompt injection risk considered where model/tool input exists
- Destructive actions require approval

## Handoff

After implementation:

```text
/session-handoff
```

Then, in a fresh context:

```text
/resume-from-handoff
```
