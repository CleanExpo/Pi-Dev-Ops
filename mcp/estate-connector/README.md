# Estate connector

One web address that Queue, Scout, Sentinel, Critic, Margot, and Projects Manager can all use. They read Unite-Group, Pi-Dev-Ops, and Mission Control through it, and they leave notes on one shared board so they can see what the others just did.

This is a remote connector (the current MCP "Streamable HTTP" style). It does not call a paid language model. It does not deploy, merge, or delete anything.

The older `mcp/pi-ceo-server.js` file stays as the local desktop connector. Do not point the bots at that file. Point them at this server's `/mcp` address.

## Address to register

After it is running on the public web:

```text
https://<the address Railway shows>/mcp?bot=<bot-name>
```

Examples:

```text
https://<host>/mcp?bot=queue
https://<host>/mcp?bot=scout
https://<host>/mcp?bot=sentinel
https://<host>/mcp?bot=critic
https://<host>/mcp?bot=margot
https://<host>/mcp?bot=projects-manager
```

Each bot also sends this header:

```text
Authorization: Bearer <ESTATE_MCP_TOKEN>
```

A bot name can be sent three ways. The first one that is present is used. If the header and the URL disagree, the call is rejected.

1. Header `X-Estate-Bot: Queue`
2. The `?bot=` part of the URL above
3. A `bot` field on a write tool

Calls with no token, or the wrong token, are rejected. The small `/healthz` check used by Railway answers `{ "status": "ok" }` and nothing else, so the platform can see that the process is up.

## Tools

Read tools only look. Write tools are marked `[WRITE]`, check the input, and append a line to the audit log: who (the bot name), what (the tool and a short summary), and when. The token is never written to that log.

| Tool | Kind | What it does |
|---|---|---|
| `coord_activity` | Read | Recent notes on the shared board. Optional filter by system. |
| `coord_post_note` | Write | Add a note. Requires a system tag: `coord`, `pidevops`, `unite`, or `mc`. |
| `pidevops_health` | Read | Live health of the Pi-Dev-Ops backend, when `PICEO_BASE_URL` is set. |
| `pidevops_projects` | Read | Project list already stored in this repo (`config/harness/projects.json`). |
| `pidevops_deployments` | Read | Deployment addresses from that same list. Does not deploy. |
| `pidevops_post_status` | Write | Post a Pi-Dev-Ops status note on the shared board. |
| `unite_status` | Read | Live Unite-Group status when `UNITE_BASE_URL` is set. Otherwise the saved project row. |
| `unite_projects` | Read | Live Unite project list only when a projects path is set. Otherwise the saved row. |
| `unite_post_note` | Write | Post an Unite-Group note on the shared board. |
| `mc_live` | Read | Mission Control live page (`/api/mission-control/live`) plus the shared queue. |
| `mc_queue` | Read | The shared queue the bots update. |
| `mc_post_note` | Write | Post a Mission Control note. |
| `mc_update_queue_item` | Write | Create or update a queue item. Status can be `open`, `blocked`, or `done`. |
| `mc_claim_work` | Write | Take an existing item. Other bots see the owner's name. |
| `mc_release_work` | Write | Put an item you claimed back to `open`. The item stays. |

There is no delete tool. A finished item is marked `done`.

## Settings

Set these on the host. Do not put the real token in git. Empty names are in `.env.example`.

| Name | Required | Meaning |
|---|---|---|
| `ESTATE_MCP_TOKEN` | Yes | Long password (at least 16 characters). Bots send it as a bearer token. The server will not start without it. |
| `PORT` | Set by Railway | Port to listen on. |
| `ESTATE_MCP_PORT` | No | Used only when `PORT` is unset. Default `8787`. |
| `ESTATE_MCP_HOST` | No | Default `0.0.0.0`. |
| `ESTATE_MCP_DATA_DIR` | No | Folder for the shared board and `audit.jsonl`. Default `mcp/estate-connector/data`. |
| `ESTATE_MCP_BOTS` | No | Comma-separated bot names. Default: Queue, Scout, Sentinel, Critic, Margot, Projects Manager. |
| `ESTATE_MCP_ALLOWED_HOSTS` | No | Comma-separated host names, if you want to limit which Host header is accepted. |
| `ESTATE_MCP_REPO_ROOT` | No | Folder that contains `config/harness/projects.json`. Found automatically when the process runs from this repo. |
| `PICEO_BASE_URL` | No | Pi-Dev-Ops backend, for live health and Mission Control. Example: `https://pi-dev-ops-production.up.railway.app` |
| `PICEO_BEARER_TOKEN` | No | Sent only to that backend. Use the backend's existing password if the live page requires a login. |
| `UNITE_BASE_URL` | No | Unite-Group site. Example: `https://unite-group.vercel.app` |
| `UNITE_BEARER_TOKEN` | No | Sent only to Unite-Group, and only if that site requires a login. |
| `UNITE_STATUS_PATH` | No | Default `/api/health`. |
| `UNITE_PROJECTS_PATH` | No | Path for a live Unite project list. Leave empty to use the saved project row. |

Without the optional URLs, read tools still answer. They say the live site is not configured and return what is already in this repo. Notes and the queue work either way, because they are stored by this connector.

## Run a check on your machine

```bash
cd mcp/estate-connector
npm install
npm test
```

To start it locally (the token below is an example, not a real secret):

```bash
ESTATE_MCP_TOKEN="replace-with-a-long-random-password" npm start
```

Then the local address is `http://127.0.0.1:8787/mcp?bot=queue`. Bots on the internet cannot reach that. Use Railway for the shared address.

## Deploy on Railway

Do this in the Railway project that already hosts Pi-Dev-Ops. Do not change the existing Python service.

1. Add a **new service** from the same GitHub repo. Leave the existing Python service as it is.
2. Set the service **root directory** to `mcp/estate-connector`. If the root stays the repo root, Railway builds the Python app instead of this connector.
3. Set the start command to `npm start` and the health check path to `/healthz`. Builder should be Nixpacks (or Railpack), not the Dockerfile.
4. Add a variable named `ESTATE_MCP_TOKEN`. Paste a long random password. Keep a copy for the bots. Do not commit it.
5. Optional, for live Mission Control and Pi-Dev-Ops health: `PICEO_BASE_URL` = the existing backend address, and `PICEO_BEARER_TOKEN` = the password that backend already uses.
6. Optional, for live Unite-Group: `UNITE_BASE_URL` = `https://unite-group.vercel.app`.
7. Add a **volume** mounted at `/data`, and set `ESTATE_MCP_DATA_DIR=/data`. Without a volume, the shared notes disappear the next time the service is redeployed.
8. Deploy. Copy the public `https://` address Railway shows.
9. In each bot, register `https://<that address>/mcp?bot=<bot-name>` and the bearer token from step 4.

This does not merge the pull request, does not create the token for you, and does not turn the service on.

## Adding a project later

One folder per project, registered in one file: `adapters/registry.js`.

Unite-Group is the pattern to copy. `adapters/unite/index.js` is a few lines that call `httpProjectAdapter(...)`. A later project is the same: new folder, one export, one line in the registry. Read tools should use a base URL from the environment. Write tools should only post notes or queue updates on this shared board, and must go through the audited write helper. Do not add delete, deploy, or merge tools.

These are not connected in this version. What each one still needs:

| Project | Registry id | Already known | Still needed before live reads work |
|---|---|---|---|
| RestoreAssist | `restoreassist` | Repo `CleanExpo/RestoreAssist`. Site `https://restoreassist.app`. | A status path on that site, then `RESTOREASSIST_BASE_URL`. A bearer token only if the path is private. |
| Synthex | `synthex` | Repo `CleanExpo/Synthex`. Site `https://synthex.social`. | A status path, then `SYNTHEX_BASE_URL`. |
| CCW-CRM | `ccw-crm` | Repo `CleanExpo/CCW-CRM`. Linear name CCW-ERP/CRM. | The project list has no public address yet. Need the live URL and a status path. |
| DR-NRPG | `dr-nrpg` | Repo `CleanExpo/DR-NRPG`. A probe in this repo already calls `https://dr-nrpg-platform.vercel.app/api/health`. | Point the adapter at that health URL after confirming it is still the right one. |
| Disaster-Recovery | `disaster-recovery` | The registry row now points at sandbox repo `CleanExpo/DR-Sandbox` (the old repo was `CleanExpo/Disaster-Recovery`). | No deployment address is stored. Need the public site URL and a status path. |
| ATO | `ato` | Repo `CleanExpo/ATO`. | No deployment address is stored. Need the public site URL and a status path. |
| CARSI | `carsi` | Repo `CleanExpo/carsi`. The name `carsi.com.au` appears in Margot's notes. | No deployment address is stored. Confirm the public URL and a status path. |

Queue notes for any of those can wait until the adapter exists. The shared board already accepts only the system ids that are registered.
