# Estate connector

One web address that Queue, Scout, Sentinel, Critic, Margot, and Projects Manager can all use. They share one login and one notebook, so each bot can see what the others just did.

It can look at Unite-Group, Pi-Dev-Ops, and Mission Control. It can leave a note, update a shared queue item, and claim or release that item. It cannot delete data, merge code, or deploy anything.

## Why it lives here

Pi-Dev-Ops is the home because Mission Control's live view is already served by this repo, and the project register (`config/harness/projects.json`) already lists both Unite-Group and Pi-Dev-Ops.

Three older servers stay as they are. This connector does not replace them:

| What | Where | Why it is not the shared connector |
| --- | --- | --- |
| Pi-CEO desktop server | `mcp/pi-ceo-server.js` | Talks only to the machine it is running on. It can also run code, ship a build, and call a paid research API. |
| Operator app | Unite-Group `packages/pi-ceo-operator-mcp` | A local screen for one person. No login. Two read-only tools. |
| Veritas kanban | Unite-Group `apps/web/packages/veritas-kanban-mcp` | Talks to a local kanban board, not Mission Control. |

Mission Control's queue on screen comes from Linear, through this repo's `/api/mission-control/live` route. That route wants a dashboard login, which a bot does not have. When `LINEAR_API_KEY` is set, the connector reads that same "Ready for Pi-Dev" queue directly. When it is not set, the tool says the queue is not configured instead of guessing.

## Address to give each bot

```text
https://<the host Railway gives you>/mcp
```

Login header, on every call:

```text
Authorization: Bearer <ESTATE_MCP_TOKEN>
```

Optional header, so a write is rejected if the bot signs a note as someone else:

```text
X-Bot-Name: Queue
```

This is the current remote MCP style (Streamable HTTP). The server answers with a normal JSON body. A check that the process is up, with no secrets in it, is `https://<host>/healthz`.

The token is one shared password for all of these bots. The name in `actor` is a label in the notebook, not a second password.

## Tools

Reads only look. Writes change the shared notebook on this server. They do not edit Linear, GitHub, or the live site.

### Read

| Tool | What you get |
| --- | --- |
| `unite_status` | Unite-Group repo snapshot, plus a reminder of the older apps above |
| `unite_health` | Whether GitHub is configured, and whether that repo answered |
| `unite_projects` | Unite-Group rows in the project register |
| `unite_queue` | Shared items tagged unite, plus Unite's Ready for Pi-Dev issues when Linear is set |
| `unite_deployments` | Recorded Unite https addresses. `probe: true` requests each one |
| `pidevops_status` | Pi-Dev-Ops health, queue counts, and recorded addresses |
| `pidevops_health` | Pi-CEO `/health`. Detail appears only when `PICEO_BEARER` is set |
| `pidevops_projects` | Pi-Dev-Ops and Margot rows in the project register |
| `pidevops_queue` | Shared items tagged pidevops, plus those projects' Ready for Pi-Dev issues |
| `pidevops_deployments` | Recorded Pi-Dev-Ops and Margot https addresses |
| `mc_status` | Recent shared notes, queue counts, and the Mission Control live route if it answers |
| `mc_health` | Pi-CEO health, and whether `/api/mission-control/live` answered |
| `mc_projects` | Every project Mission Control is allowed to claim |
| `mc_queue` | The shared queue, plus the Linear queue Mission Control shows |
| `coord_list_activity` | Newest notes, claims, releases, and queue updates |
| `coord_list_audit` | Newest write attempts: who, which tool, when, accepted or refused |

### Write

Each write says `WRITE` in its title and description. The server checks the inputs, scrubs pasted tokens, and appends an audit row (who, what, when) before it returns.

| Tool | What it does |
| --- | --- |
| `coord_post_note` | Adds a note to the shared feed |
| `mc_update_queue_item` | Adds or updates a shared queue item. It cannot claim the item; use the claim tool |
| `mc_claim_work` | Claims an item that is free, or already yours. Refuses if another bot holds it |
| `mc_release_work` | Lets go of an item you hold. The item stays on the list, marked open |

There is no delete, merge, or deploy tool.

## Environment variables

Set these on the host. Do not put real values in git. Names match `.env.example`.

| Name | Required | Purpose |
| --- | --- | --- |
| `ESTATE_MCP_TOKEN` | Yes | Shared bearer. At least 16 characters. If it is missing or shorter, every bot call is rejected and `/healthz` stays unhealthy. |
| `ESTATE_MCP_ACTORS` | No | Comma-separated names allowed to write. Example: `Queue,Scout,Sentinel,Critic,Margot,Projects Manager`. Empty means any well-formed name. |
| `ESTATE_MCP_STATE_DIR` | No | Folder for the notebook, queue, and audit log. Default is `.harness/estate-mcp` inside the repo checkout. |
| `PICEO_BASE_URL` | No | Pi-CEO API. Default `https://pi-dev-ops-production.up.railway.app`. |
| `PICEO_BEARER` | No | Same value as `TAO_PASSWORD`. Unlocks the detailed `/health` body. It does not unlock the Mission Control live route. |
| `GITHUB_TOKEN` | No | Read-only GitHub status. No GitHub call is made when this is empty. |
| `LINEAR_API_KEY` | No | Read-only Ready for Pi-Dev list. No Linear call is made when this is empty. |
| `ESTATE_PROJECTS_PATH` | No | Override for `config/harness/projects.json`. |
| `PORT` | No | Defaults to `8787`. Railway sets this for you. |
| `HOST` | No | Defaults to `0.0.0.0`. |

No tool calls a paid language-model API.

## Deploy

Do this yourself when you want the bots to reach it. Nothing in this change deploys it or creates the token.

1. In Railway, add a new service from the Pi-Dev-Ops GitHub repo. Leave the existing Pi-CEO service alone.
2. Set that service's root directory to `mcp/estate-connector`.
3. Start command: `npm start`.
4. Health check path: `/healthz`.
5. Generate a random token of at least 16 characters. Put it in `ESTATE_MCP_TOKEN` on that service. Put the same value in each bot. Do not paste it into chat or commit it.
6. Add any of the optional variables you already have (`GITHUB_TOKEN`, `LINEAR_API_KEY`, `PICEO_BEARER`). Skip the ones you do not want the bots to use.
7. Deploy, then open `https://<the new host>/healthz`. It should say `"status": "ok"`.
8. In each Grok bot, add one remote MCP connector. URL: `https://<the new host>/mcp`. Header: `Authorization: Bearer <the token>`.

The notebook is stored on the service disk. A redeploy clears that disk. If you want the notes to survive, add a Railway volume, mount it at `/data`, and set `ESTATE_MCP_STATE_DIR=/data`. Skip the volume if it would add a charge. The connector still works; the feed just starts empty after the next deploy.

## Tests

From `mcp/estate-connector`:

```bash
npm ci
npm test
```

The tests check that a missing or wrong token is rejected, that a read returns project data, and that a write lands in the shared feed and the audit log.
