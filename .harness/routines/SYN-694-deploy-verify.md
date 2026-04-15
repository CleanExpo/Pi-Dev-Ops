# Claude Code Routine: SYN-694 — Synthex Deploy Verification

## Header

| Field          | Value                                                      |
| -------------- | ---------------------------------------------------------- |
| Ticket         | SYN-694                                                    |
| Purpose        | Verify Synthex Vercel deployment health after every push to main |
| Trigger type   | GitHub event — `push` on branch `main`                    |
| Repository     | `CleanExpo/Synthex`                                        |
| Timeout        | 6 minutes total                                            |
| Created        | 2026-04-16                                                 |

---

## Trigger

```yaml
trigger:
  type: github_event
  event: push
  repository: CleanExpo/Synthex
  branch: main
```

---

## Required Secrets

Configure these in the Claude Code Routine secrets settings before activating:

| Secret name              | Description                                                           |
| ------------------------ | --------------------------------------------------------------------- |
| `VERCEL_TOKEN`           | Vercel personal access token with read access to the Synthex project  |
| `VERCEL_TEAM_ID`         | Vercel team ID that owns the Synthex project (e.g. `team_abc123`)     |
| `RAILWAY_BACKEND_URL`    | Base URL of the Pi-CEO Railway backend (e.g. `https://pi-ceo.railway.app`) |
| `ROUTINE_COMPLETE_SECRET`| Shared secret sent as `X-Routine-Secret` header on webhook callbacks  |

---

## Task Description

When a push to `CleanExpo/Synthex:main` is received, the Routine executes the following steps.

### Step 1 — Initial wait (60 s)

Wait 60 seconds to allow Vercel to register the push and begin the deployment build.

```js
const INITIAL_WAIT_MS = 60_000;
await new Promise(resolve => setTimeout(resolve, INITIAL_WAIT_MS));
```

### Step 2 — Poll Vercel for deployment state

Poll the Vercel API until the latest deployment reaches state `READY` or `ERROR`.
Maximum 10 polls, 30 seconds apart (5 minutes maximum poll window).

```js
const POLL_INTERVAL_MS = 30_000;
const MAX_POLLS = 10;

const vercelUrl =
  `https://api.vercel.com/v6/deployments?app=synthex&limit=1&teamId=${VERCEL_TEAM_ID}`;

let deploymentUrl = null;
let finalState = null;

for (let attempt = 1; attempt <= MAX_POLLS; attempt++) {
  const ts = new Date().toISOString();

  const res = await fetch(vercelUrl, {
    headers: { Authorization: `Bearer ${VERCEL_TOKEN}` },
  });

  if (!res.ok) {
    console.log(`[${ts}] Poll ${attempt}/${MAX_POLLS}: Vercel API error ${res.status}`);
    if (attempt < MAX_POLLS) await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    continue;
  }

  const data = await res.json();
  const deployment = data.deployments?.[0];
  const state = deployment?.state ?? 'UNKNOWN';
  const url = deployment?.url ? `https://${deployment.url}` : null;

  console.log(`[${ts}] Poll ${attempt}/${MAX_POLLS}: state=${state} url=${url ?? 'n/a'}`);

  if (state === 'READY') {
    deploymentUrl = url;
    finalState = 'READY';
    break;
  }

  if (state === 'ERROR') {
    finalState = 'ERROR';
    break;
  }

  if (attempt < MAX_POLLS) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
}

if (!finalState) {
  finalState = 'TIMEOUT';
}
```

### Step 3 — Health check (READY path)

If `finalState === 'READY'`, call `GET <deploymentUrl>/api/health` and verify the response is HTTP 200 with body `{"status":"ok"}`.

```js
let healthOk = false;
let healthDetail = null;

if (finalState === 'READY' && deploymentUrl) {
  const healthRes = await fetch(`${deploymentUrl}/api/health`);

  if (healthRes.status === 200) {
    const body = await healthRes.json();
    if (body?.status === 'ok') {
      healthOk = true;
    } else {
      healthDetail = `Health body unexpected: ${JSON.stringify(body)}`;
    }
  } else {
    healthDetail = `Health check returned HTTP ${healthRes.status}`;
  }
} else if (finalState === 'ERROR') {
  healthDetail = 'Vercel deployment reached ERROR state';
} else {
  healthDetail = `Deployment did not reach READY within ${MAX_POLLS} polls`;
}
```

### Step 4 — Failure callback

If `finalState === 'ERROR'`, `finalState === 'TIMEOUT'`, or health check failed, POST to Railway with failure payload.

```js
const RAILWAY_WEBHOOK = `${RAILWAY_BACKEND_URL}/api/webhook/routine-complete`;

if (!healthOk) {
  const failPayload = {
    routine: 'SYN-694',
    status: 'failed',
    detail: healthDetail ?? 'Unknown failure',
  };

  console.log(`[FAIL] Posting failure to Railway: ${JSON.stringify(failPayload)}`);

  await fetch(RAILWAY_WEBHOOK, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Routine-Secret': ROUTINE_COMPLETE_SECRET,
    },
    body: JSON.stringify(failPayload),
  });
}
```

### Step 5 — Success callback

If health check passed, POST to Railway with success payload.

```js
if (healthOk) {
  const successPayload = {
    routine: 'SYN-694',
    status: 'success',
    deployment_url: deploymentUrl,
  };

  console.log(`[OK] Posting success to Railway: ${JSON.stringify(successPayload)}`);

  await fetch(RAILWAY_WEBHOOK, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Routine-Secret': ROUTINE_COMPLETE_SECRET,
    },
    body: JSON.stringify(successPayload),
  });
}
```

---

## Full Routine Script

The sections above are broken out for clarity. The production script is the concatenation of all steps in order. Paste this into the Claude Code Routine editor:

```js
// SYN-694 — Synthex Deploy Verification Routine
// Trigger: push to CleanExpo/Synthex:main

const VERCEL_TOKEN = process.env.VERCEL_TOKEN;
const VERCEL_TEAM_ID = process.env.VERCEL_TEAM_ID;
const RAILWAY_BACKEND_URL = process.env.RAILWAY_BACKEND_URL;
const ROUTINE_COMPLETE_SECRET = process.env.ROUTINE_COMPLETE_SECRET;

const INITIAL_WAIT_MS = 60_000;
const POLL_INTERVAL_MS = 30_000;
const MAX_POLLS = 10;
const RAILWAY_WEBHOOK = `${RAILWAY_BACKEND_URL}/api/webhook/routine-complete`;

// Step 1: Initial wait
console.log(`[${new Date().toISOString()}] Waiting ${INITIAL_WAIT_MS / 1000}s for Vercel to register push...`);
await new Promise(resolve => setTimeout(resolve, INITIAL_WAIT_MS));

// Step 2: Poll Vercel
const vercelUrl = `https://api.vercel.com/v6/deployments?app=synthex&limit=1&teamId=${VERCEL_TEAM_ID}`;
let deploymentUrl = null;
let finalState = null;

for (let attempt = 1; attempt <= MAX_POLLS; attempt++) {
  const ts = new Date().toISOString();
  const res = await fetch(vercelUrl, {
    headers: { Authorization: `Bearer ${VERCEL_TOKEN}` },
  });

  if (!res.ok) {
    console.log(`[${ts}] Poll ${attempt}/${MAX_POLLS}: Vercel API error ${res.status}`);
    if (attempt < MAX_POLLS) await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    continue;
  }

  const data = await res.json();
  const deployment = data.deployments?.[0];
  const state = deployment?.state ?? 'UNKNOWN';
  const url = deployment?.url ? `https://${deployment.url}` : null;

  console.log(`[${ts}] Poll ${attempt}/${MAX_POLLS}: state=${state} url=${url ?? 'n/a'}`);

  if (state === 'READY') { deploymentUrl = url; finalState = 'READY'; break; }
  if (state === 'ERROR') { finalState = 'ERROR'; break; }
  if (attempt < MAX_POLLS) await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
}

if (!finalState) finalState = 'TIMEOUT';

// Step 3: Health check
let healthOk = false;
let healthDetail = null;

if (finalState === 'READY' && deploymentUrl) {
  const healthRes = await fetch(`${deploymentUrl}/api/health`);
  if (healthRes.status === 200) {
    const body = await healthRes.json();
    healthOk = body?.status === 'ok';
    if (!healthOk) healthDetail = `Health body unexpected: ${JSON.stringify(body)}`;
  } else {
    healthDetail = `Health check returned HTTP ${healthRes.status}`;
  }
} else if (finalState === 'ERROR') {
  healthDetail = 'Vercel deployment reached ERROR state';
} else {
  healthDetail = `Deployment did not reach READY within ${MAX_POLLS} polls (state: ${finalState})`;
}

// Steps 4 & 5: Callback to Railway
const payload = healthOk
  ? { routine: 'SYN-694', status: 'success', deployment_url: deploymentUrl }
  : { routine: 'SYN-694', status: 'failed', detail: healthDetail ?? 'Unknown failure' };

console.log(`[${new Date().toISOString()}] Posting to Railway: ${JSON.stringify(payload)}`);

await fetch(RAILWAY_WEBHOOK, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Routine-Secret': ROUTINE_COMPLETE_SECRET,
  },
  body: JSON.stringify(payload),
});

console.log(`[${new Date().toISOString()}] SYN-694 complete. Status: ${payload.status}`);
```

---

## Implementation Notes

- `fetch()` is natively available in Claude Code Routines — no polyfill needed.
- All secrets must be configured in the Routine's environment settings; never hardcode them.
- Total maximum runtime: 60 s initial wait + (10 × 30 s) polls + health check ≈ **6 minutes**, within the 6-minute timeout.
- Each poll logs a timestamped line for audit trail visibility in the Routine run logs.
- The Railway webhook endpoint must validate `X-Routine-Secret` to prevent spoofed callbacks.
