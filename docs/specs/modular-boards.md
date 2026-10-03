# Modular Mission Control boards — spec

**Ticket:** RA-7898 · **Branch:** `feature/RA-7898-modular-boards` · **Base:** `main` @ `e3dff5e`
**App:** `dashboard/` (Next 16, React 19, Tailwind 4, zustand) · **Layout library:** `react-grid-layout@2.2.4`

## Review record

| Round | Spec revision | Reviewer model | Axes | Verdict | Blocking findings |
|---|---|---|---|---|---|
| 1 | `fdbe99f` | Composio `invoke_llm` (vendor undisclosed; see note) | standards | FAIL | refresh-after-write untested; done-clause omits T/G tests; pasted "Today" rates; `/loop` + section pages untested for "unchanged"; no in-board write test |
| 1 | same | same | spec vs brief | FAIL | sessions/health routing unclear (N1); FixSessionLive second interval; action views hidden on failure would remove the kill control |
| 1 | same | same | spec vs route files | FAIL | mesh-fleet no_source rows uncited; kill-switch 401 body misquoted |
| 1 | same | same | spec (single combined call) | NO VERDICT — reviewer returned no output twice; not counted as a pass, replaced by the two split calls above | — |
| 2 | `b880806` | same | standards | PASS | — (6 non-blocking, addressed in round 3 text) |
| 2 | same | same | spec vs route files | PASS | — |
| 2 | same | same | spec vs brief | FAIL | wrapped provider-usage / wiki-graph components would add a second reader (one-request rule) |
| 3 | `0a4ed28` | same | spec vs route files | PASS | — |
| 3 | same | same | spec vs brief (run twice) | PASS, PASS | — (non-blocking notes addressed in text) |
| 3 | same | same | standards | FAIL | A6 did not list every page it claims unchanged |
| 3-fix | this revision | same | standards, finding F1 only | see below | The reviewer's own proposed fix was applied verbatim (A6 now lists all 21 pages). Round 3 was the last full round the brief allows, so this is a single confirmation that F1 is closed, not a fourth review |

Reviewer note: neither Codex nor an OpenRouter key is available in this session's environment
(no `codex` binary, no `OPENROUTER_API_KEY`). The reviewer is the LLM behind Composio's workbench
`invoke_llm`; asked twice, it would not name its model or vendor. It ran in a separate service with
only the brief, the spec, `CLAUDE.md` excerpts and the named baseline files — none of the builder's
reasoning. Because its vendor cannot be confirmed non-Anthropic, record it as a **weaker control
than the brief asks for**.

## 1. Outcome

The founder can open `/control/boards`, see a board of modules, and — after pressing **Customize** —
move, resize, add (from a library grouped by sector), remove and re-skin modules, and switch each
module between several visuals ("views"). Boards survive reload. A wall screen can open a board
full-screen at `/control/boards/kiosk?board=<preset>&machine=<host>`.

Done means: every test in §9 passes — acceptance tests A1–A10, each shown failing on a control arm
first, and the unit tests T1–T7 and governance tests G1–G4 — plus `npx tsc --noEmit`,
`npm run build` and `bash scripts/handoff-loop.sh` green. A test not listed in §9 does not gate.

## 2. Four layers

All new logic lives under `dashboard/lib/boards/`. React parts live under
`dashboard/components/boards/`.

| Layer | Location | Owns | Must not own |
|---|---|---|---|
| Sources | `lib/boards/sources/` | One shared poller per feed, request de-duplication, normalised state, freshness | Rendering |
| Registry | `lib/boards/registry/` | Module definitions: id, name, sector, source ids, min size, action flag, views | Fetching, layout |
| Boards | `lib/boards/{board,store,presets}` + `components/boards/` | Board JSON, grid canvas, edit mode, library, presets, BoardStore | Data, colours |
| Looks | `app/globals.css` (one token set) + `data-board-skin` on the board root | Colour, type scale, radius | Anything structural |

A layer may only depend on the layers above it in this table. A look changes no module code.

## 3. Sources

### 3.1 Poller contract

`lib/boards/sources/` exports `useSource(id)` and `resetSources()`.

- **One poller per feed, reference-counted.** The first subscriber starts it (immediate fetch,
  then one timer at the feed's interval). Each later subscriber shares it. The last unsubscribe
  stops the timer. N copies of a module, or N modules on one feed, make **one** request per
  interval.
- **In-flight guard.** A tick that lands while a request is outstanding is skipped, not queued.
- **Timeout.** Every request carries a 10 s abort. An aborted request counts as a failed read.
- **Manual refresh.** `refresh(id)` triggers one immediate read, used after an action module's
  existing write succeeds (kill / resume, idea dispose). It does not start a second timer. (A
  HealthGrid "Fix with Claude" build already opens its own live log; it calls no refresh.)
- **Declared additions beyond the brief:** the 10 s abort, the in-flight guard and `refresh(id)`.
  The abort and in-flight guard are what `SwarmPanel` and `useOperatorObservations` already do on
  `main`; sharing a poller across panels without them would let one hung request block every
  consumer. `refresh(id)` replaces the after-action re-read that `KillSwitchPanel` and
  `IdeaPipelinePanel` already perform with their own fetch.
- **Test reset.** `resetSources()` stops every timer and drops every cache. `vitest.setup.ts` calls
  it in a global `afterEach`, so per-case `fetch` stubs never see another case's cache. Pattern
  follows the `_resetWallCache()` hook in `lib/wall/source.ts:30`.
- **Same-origin only.** A source reads exactly the URL in §3.3. Pi-CEO backend paths go through
  `fetchProxy` in `lib/pi-ceo-fetch.ts` and nowhere else.
- **GET only.** The sources layer issues no request with a method other than GET.

### 3.2 Normalised state

Every feed resolves to exactly one of five states:

| State | Meaning | What a module shows |
|---|---|---|
| `loading` | No read has finished since the poller started | "Loading" in the frame; no number |
| `live` | The latest read succeeded and its data is younger than the feed's stale age | The view |
| `stale` | Data exists but the latest read failed, or the data's own timestamp is older than the stale age | "Stale — last good read Xs ago" in the frame; the view is not rendered, so no number |
| `unreachable` | The latest read failed and no good data exists; or the response says the upstream did not answer; or 401 | "Unreachable — <reason>" in the frame; no number |
| `no_source` | The feed says it is not configured, or the module has no live source | Grey hollow "No source yet — <reason>"; no number |

Stale age for every feed = `3 × interval` (minimum 15 s). The factor is the one already used on
`main`: `lib/wall/client.ts` sets `STALE_AFTER_MS = POLL_MS * 3`, and `LiveActivityFeed` calls its
5 s feed live only if the last update is under 15 s old.

A module's state is the worst of its sources, in the order
`unreachable > no_source > stale > loading > live`.

### 3.3 Feeds, intervals and failure readers

One interval per feed. The "Today" column is the rate in each panel on `main` @ `e3dff5e`, re-derived by:

```bash
cd dashboard && grep -nE "setInterval\(|POLL_MS =" components/control/{FleetTile,LiveActivityFeed,PortfolioFocus,SwarmPanel,ModelFabricPanel,HealthGrid,CuratorProposalsPanel,KillSwitchPanel}.tsx \
  hooks/useOperatorObservations.ts lib/wall/client.ts components/command-centre/provider-usage/ProviderUsageCockpit.tsx
```

The `LiveActivityFeed` 1 s line is its clock, not a poll. `IdeaPipelinePanel` and `WikiGraphTile` have no
`setInterval` (read on mount only).

| Feed id | URL | Interval | Today | Reason for the chosen interval |
|---|---|---|---|---|
| `mesh-fleet` | `/api/mesh-fleet` | 20 s | 20 s (FleetTile) | Heartbeats land every few minutes; 20 s is what FleetTile already uses |
| `wall` | `/api/mesh-fleet/wall` | 5 s | 5 s (Wall) | The wall marks a snapshot stale at 15 s; slower polling would flap |
| `model-fabric` | `/api/model-fabric` | 15 s | 15 s | Unchanged |
| `swarm-status` | `/api/swarm-status` | 30 s | 30 s | Unchanged; `control-telemetry-refresh.test.tsx` pins 30 s |
| `kill-switch` | `/api/kill-switch?op=status` | 10 s | 10 s | Safety control: keep the fastest existing rate |
| `provider-usage` | `/api/command-centre/provider-usage` | 30 s | 30 s | Unchanged |
| `wiki-graph` | `/api/command-centre/wiki-graph` | 300 s | once on mount | Counts change on a sync, not minute to minute |
| `curator` | `/api/curator-proposals?status=pending&limit=10` | 30 s | 30 s | Unchanged; the query is the one `CuratorProposalsPanel` sends today |
| `pi-health` | `/api/pi-ceo/health` (via `fetchProxy`) | 15 s | 15 s (overview) | Unchanged; `operator-readiness.test.tsx` pins 15 s |
| `sessions` | `/api/pi-ceo/api/sessions` (via `fetchProxy`) | 15 s | 4 s / 15 s (the grep below finds no 5 s sessions poll; the brief's "5 s" is `LiveActivityFeed`'s `mc-live` poll, whose payload carries `active_sessions` — a different feed) | The overview rate; `FixSessionLive`'s 4 s fallback folds in (note N2) |
| `projects-health` | `/api/pi-ceo/api/projects/health` (via `fetchProxy`) | 30 s | 30 s and 60 s | Scan scores move hourly; 30 s keeps PortfolioFocus's rate |
| `mc-live` | `/api/pi-ceo/api/mission-control/live` (via `fetchProxy`) | 5 s | 5 s and 30 s | The live feed's "live" label means a read in the last 15 s |
| `idea-pipeline` | `/api/pi-ceo/api/idea-pipeline` (via `fetchProxy`) | 60 s | on mount + after actions | Ideas arrive by hand; `refresh()` covers the after-action read |
| `pipelines` | `/api/pi-ceo/api/pipelines` (via `fetchProxy`) | 30 s | 30 s | Unchanged |
| `local-clock` | none (browser clock) | 1 s, local | — | A clock is not a feed; always `live` |
| `static` | none (text in the bundle) | — | — | Always `live`; the text cites its file |

**Note N1 — which `/api/sessions` and `/health`.** The brief names "/api/sessions + /health
(hooks/useOperatorObservations.ts)". That hook reads both through `fetchProxyJSON`
(`hooks/useOperatorObservations.ts:20,26`), so the URLs on the wire are `/api/pi-ceo/health` and
`/api/pi-ceo/api/sessions`. The dashboard's own `app/api/sessions/route.ts` is a different,
Supabase-backed route that the hook does not call; it is not a feed here. Both feeds therefore go
through `fetchProxy`, and `proxy_fallback_lint.py` covers them.

**Note N2 — one interval for `sessions`.** `FixSessionLive` in `HealthGrid.tsx` polls
`/api/sessions` every 4 s as a fallback beside its EventSource log stream. It moves onto the shared
`sessions` source (15 s). The EventSource stays the primary live surface; only the fallback slows.
Declared delta D2.

Failure readers — one per feed, each with a unit test (§9 T1):

| Feed | Success | Read as `unreachable` | Read as `no_source` | Server timestamp |
|---|---|---|---|---|
| `mesh-fleet` | 200 `{status:"ok"}` | 503 `{status:"unavailable"}` whose `reason` is "upstream unreachable" (`app/api/mesh-fleet/route.ts:38`) or "fleet snapshot missing" / "machines source failed" (`lib/control/mesh-fleet.ts:73,76`); network error; any other non-200 | 503 `{status:"unavailable"}` whose `reason` is "mesh secret not configured" or "Pi-CEO URL not configured" (`route.ts:33,35`). Same 503, read by its `reason`: these two are configuration absent, which `lib/wall/source.ts:22-23` already classifies as `no_source` for the same two conditions | `checkedAt` |
| `wall` | 200, `fleet.status:"ok"` | 200 `fleet.status:"broken"`; non-200; network | 200 `fleet.status:"no_source"` | `generated_at` |
| `model-fabric` | 200 | 503 (any body); other non-200; network | — | none (browser time) |
| `swarm-status` | 200 with `state` ≠ `"UNKNOWN"` | 200 `state:"UNKNOWN"` (the route's own fallback); non-200; network | — | none |
| `kill-switch` | 200 with no `error` | 200 with `error` other than "not configured"; 401 `{error:"Unauthorised"}` (`app/api/kill-switch/route.ts:68`), shown as "Signed out — sign in again (401)"; other non-200; network | 200 `error` containing "not configured" (`route.ts:79`) | none |
| `provider-usage` | 200 | 500; non-200; network | — | `generatedAt` (`lib/command-centre/provider-usage.ts:101,216`) |
| `wiki-graph` | 200 with `source` ≠ `"unconfigured"` | non-200; network | 200 `source:"unconfigured"` | none (`lastSync` is shown, not used for freshness) |
| `curator` | 200 with no `error` | 200 with `error` other than "not configured"; non-200; network | 200 `error` containing "not configured" | none |
| `pi-health`, `sessions`, `projects-health`, `mc-live`, `idea-pipeline`, `pipelines` | `fetchProxy` returns `ok:true` | `fetchProxy` returns `ok:false` for any reason (proxy fallback with `X-Upstream-Status`, non-200, network); `mc-live` also when the body has `error` | — | `mc-live`: `ts`; others none |

Where the server sends no timestamp, the freshness chip reads "fetched Xs ago (browser time)".
Unknown stays unknown: in every state other than `live`, `ModuleFrame` renders no view, so no
number from the view reaches the screen (G4 checks this per view); views contain no sample rows
(T5 checks that no file under `components/boards/` or `lib/boards/` other than `lib/boards/presets/`
defines a literal array of data rows).

## 4. Registry

`lib/boards/registry/` holds one file per sector plus an index; every file under 300 lines.

A module definition:

```ts
interface ModuleDef {
  id: string;            // registered id, the only thing a board may reference
  name: string;          // sentence case
  sector: "Machines" | "Delivery" | "Compute" | "Businesses" | "Safety" | "Knowledge" | "Founder" | "Utility";
  sources: string[];     // feed ids from §3.3, at least one
  minSize: { w: number; h: number };
  action: boolean;       // true when any view can trigger a write
  views: Record<string, { label: string; size: { w: number; h: number }; component: ComponentType }>;
  blurb: string;         // one line for the library
}
```

`ModuleFrame` (in `components/boards/`) renders, for every module and view: the kicker
"<sector> · <state>" with a status dot, the sentence-case title, one ⋯ menu (Show as / source /
Remove), the freshness chip and the five states. No view re-implements them.

- **Read-only views** render **only** when the module state is `live`; the frame owns every other
  state and shows its state message instead.
- **Action views** (the view #1 of a module with `action: true`) render in every state except
  `loading`, under the frame's state banner and reason. A safety control must never disappear
  because a read failed: `KillSwitchPanel` keeps "Halt swarm" available on an upstream failure
  today (`__tests__/kill-switch-panel.test.tsx`, "ERROR" cases), and a board must not remove it.
  These panels already render unknown values as "unknown" / an error line, not as numbers; A3
  checks that on the board.
- **Signed out (401).** When the `kill-switch` source answered 401, `KillSwitchPanel`'s Halt and
  Resume buttons are disabled and the reason "Signed out — sign in again (401)" is shown beside
  them (A5). This is the one new behaviour inside a view #1 panel; a POST from a signed-out browser
  would be refused by the same route anyway. Other action panels are unchanged in this pass.

### 4.1 Module list

| Id | Name | Sector | Sources | Action | View #1 (existing panel, unchanged) | Second views |
|---|---|---|---|---|---|---|
| `fleet` | Fleet | Machines | `mesh-fleet` | no | `FleetTile` | Heartbeat strip, Compact list |
| `wall-fleet` | Fleet board | Machines | `wall` | no | `FleetTiles` (wall) | — |
| `ship-chain` | Ship chain | Delivery | `wall` | no | `StationAccordion` (wall) | Station row, Ring |
| `wall-banner` | Attention banner | Founder | `wall` | no | `WallBanner` (wall) | — |
| `activity` | Live activity | Delivery | `mc-live` | no | `LiveActivityFeed` | Timeline, Pulse |
| `ideas` | Ideas | Delivery | `idea-pipeline` | **yes** | `IdeaPipelinePanel` | Funnel, Inbox |
| `portfolio` | Business health | Businesses | `projects-health`, `mc-live`, `pipelines` | no | `PortfolioFocus` | Bars, Heat, Leaderboard |
| `health` | Project health | Businesses | `projects-health` | **yes** | `HealthGrid` | — |
| `builds` | Builds | Delivery | `sessions` | no | none — new module, no existing panel; first view "Board by stage" is a new view under the new-view rules | Table, Big number |
| `swarm` | Swarm | Safety | `swarm-status`, `kill-switch` | **yes** | `SwarmPanel` | — |
| `kill-switch` | Kill switch | Safety | `kill-switch` | **yes** | `KillSwitchPanel` | Status light, Detail |
| `models` | Model routing | Compute | `model-fabric` | no | `ModelFabricPanel` | Bars, Ring, Table |
| `provider-usage` | Provider usage | Compute | `provider-usage` | no | `ProviderUsageCockpit` (wrapped, unedited) | — |
| `curator` | Curator proposals | Knowledge | `curator` | no | `CuratorProposalsPanel` | — |
| `wiki-graph` | Wiki graph | Knowledge | `wiki-graph` | no | `WikiGraphTile` (wrapped, unedited) | — |
| `north-star` | North Star | Founder | `static` | no | none — new module; first view "Banner" | Compact |
| `clock` | Brisbane time | Utility | `local-clock` | no | none — new module; first view "Digital" | Analog |

"Unchanged" means: on `/control`, `/control/<section>`, `/loop` and `/command-centre/*` each panel
renders identically before and after, given the same responses; inside a board it renders the
same markup inside the frame. Each converted panel reads its data from `useSource` instead of its
own `setInterval`; its markup, copy and classes do not change.

`ProviderUsageCockpit` and `WikiGraphTile` are provenance-baselined
(`__tests__/command-centre-readonly.test.ts`) and are not edited. Their modules wrap them from
outside. Both components call the global `fetch` themselves, so a shared poller alone would add a
second reader. To keep one request per interval without editing them, the boards page installs a
**request-sharing tap** (`lib/boards/sources/fetch-tap.ts`) for exactly two URL paths —
`/api/command-centre/provider-usage` and `/api/command-centre/wiki-graph`:

- It wraps `window.fetch` only while a board page is mounted, and restores the original on unmount.
- Only GET requests whose path is one of the two is touched; every other request passes straight
  through to the original `fetch` unchanged.
- A matching GET joins an in-flight request for the same path, or receives a clone of the last
  response if that response is younger than the feed's interval minus 1 s; otherwise it goes to the
  network. Each network response is also handed to the shared source, so the frame's state comes
  from the same read the component made.
- Net effect, pinned by T7: with N provider-usage modules on a board, exactly one
  `/api/command-centre/provider-usage` network request per 30 s; with N wiki-graph modules, one per
  300 s.

This is the only global patch in the diff. It is scoped to two paths and the board page's lifetime,
and T7 also asserts that a request to any other path reaches the original `fetch` untouched.

The `Wall` component (`components/wall/Wall.tsx`) and `/command-centre/wall` are not edited and
keep their own 5 s poll. Board modules on the `wall` feed use the shared source. Declared delta D1:
a board with wall modules open beside `/command-centre/wall` in the same browser makes two wall
reads per 5 s, one per page.

### 4.2 Declared deltas

Every visible or behavioural difference from `main` that this pass introduces on purpose:

| # | Delta | Where |
|---|---|---|
| D1 | A board with wall modules open beside `/command-centre/wall` in the same browser makes two wall reads per 5 s (one per page; `Wall.tsx` is not edited) | wall feed |
| D2 | `FixSessionLive`'s fallback poll slows from 4 s to the shared 15 s (N2) | HealthGrid drill-down |
| D3 | On a board, a read-only view is hidden while its module is `stale`, `unreachable` or `no_source`, and the frame shows the state instead. On the existing pages the panels keep today's behaviour | boards only |
| D4 | On a board, an action view #1 renders under the frame's state banner (kicker, title, state, reason). The panel's own markup inside the frame is unchanged (T8) | boards only |
| D5 | Signed out (401): the kill switch's Halt / Resume are disabled with the reason shown (A5). Applies on the existing pages too, because it lives in the panel | KillSwitchPanel |
| D6 | New modules with no existing panel — `builds`, `north-star`, `clock` — are additions; their first views follow the new-view rules | registry |
| D7 | `wiki-graph` is re-read every 300 s on a board, where today the tile reads once on mount | wiki-graph feed |

## 5. Boards

**Board JSON** (exported and imported verbatim; same shape as the Board Builder prototype):

```json
{ "name": "Desk", "skin": "paper",
  "items": [{ "id": "fleet-1", "module": "fleet", "view": "tile" }],
  "layouts": { "lg": [{ "i": "fleet-1", "x": 0, "y": 0, "w": 7, "h": 4 }], "md": [], "sm": [] } }
```

- Grid: breakpoints `lg 960 / md 600 / sm 0`, columns `12 / 8 / 4`. Missing `md`/`sm` layouts are
  derived by react-grid-layout from `lg`.
- `react-grid-layout@2.2.4`, v2 API: `Responsive` + `useContainerWidth`; render the grid only once
  mounted (width known); `dragConfig {enabled, handle, cancel}`; `resizeConfig {enabled, handles}`.
- **Presets** — `lib/boards/presets/*.json`: `desk`, `wall-1` … `wall-6`, `founder-brief`. Each is
  validated by a test: every item references a registered module and view, every layout item
  matches an item id, every size ≥ the module's min size.
- **Validation on load.** A board from storage or import is parsed by one function. Invalid JSON
  or a wrong shape is rejected with an error message; the stored board is not overwritten. An item
  whose module id is not registered renders a grey "Unknown module" frame with only a Remove
  action — never a capability. An unknown view id falls back to the module's first view.
- **BoardStore** — one interface: `list()`, `get(id)`, `save(id, board)`, `remove(id)`,
  `exportJSON(id)`, `importJSON(text)`. One implementation now: browser `localStorage`, key
  `pi-boards-v1`, all access in try/catch, presets used when storage is empty or unreadable.
  Server-side storage is a founder decision (§11); this pass designs the interface only — no table,
  no route.
- **Page** `/control/boards` — protected by the existing `/control` entry in
  `PROTECTED_PAGE_PREFIXES` (`proxy.ts`). Not added to `CONTROL_SECTIONS`
  (`control-subpages.test.ts` pins the section count — re-derive with
  `grep -n "toHaveLength" dashboard/__tests__/control-subpages.test.ts`). Own nav link in `ControlSubnav`.
- **Locked by default.** "Customize" unlocks: drag (handle = card title), resize (corner handle),
  add from a library drawer grouped by sector (pick a view to add), remove, view chips under each
  card. Also: board tabs, "+ Board", "Reset to preset", export/import JSON.
- **Kiosk** `/control/boards/kiosk?board=<preset>&machine=<host>` — full-screen, Wall look, locked,
  no edit controls. Resolves **repo presets only** until server storage exists; an unknown preset
  shows an error naming the valid ids. `machine` is passed to the wall fleet view as the kiosk's
  own host. Not under `/command-centre`; `/command-centre/wall` untouched.

## 6. Looks

Built last. Matches the second version of the "Mission Control Board Builder" prototype
(claude.ai artifact `5FhijazFi9TM5qSvCJV99Q`, read on 3 Oct 2026): its token set and card anatomy
are the reference. §6 is checked in two ways: the mechanical rules below are tests (T5); the
overall look is a founder visual review of the screenshots in the handoff, and is not a gate.

- **Card anatomy:** small uppercase kicker "<sector> · <status>" with a status dot; sentence-case
  title; one ⋯ menu holding "Show as" (views), the source, and Remove. No per-card footer, no
  dropdown boxes, no uppercase titles.
- **Colour (guidance, reviewed by eye):** one data accent per look; green / amber / red for states
  that need attention; grey hollow for "no source yet".
- **Board header:** greeting with a one-line summary, quick-action chips (links to existing pages
  only), a single "Updated Xs ago", board tabs, "Customize".
- **Looks** as token overrides on the board root (`data-board-skin`): **Paper** (default desk: warm
  paper ground, white cards, indigo accent), **Graphite** (Linear-style near-black), **Slate**
  (Mercury-style soft indigo-grey), **Wall** (Graphite, larger type). One token set in
  `app/globals.css`. Root `DESIGN.md` and `.claude/DESIGN.md` are first diffed against each other and
  any existing disagreement on tokens is resolved, then both record the four looks; CI lints the
  latter. No net-new `lucide-react` imports.
- Hex literals are banned in new files under `components/boards/` and `lib/boards/` (T5 greps
  them); converted view #1 files keep theirs. Card titles are rendered from the registry's
  sentence-case `name` with no `uppercase` class (T5 checks `ModuleFrame`).
- Sequencing: second views are built only after the board canvas works (A1, A2, A4 green), as the
  brief orders.
- Pattern references (no paid Mobbin pull in this pass): Linear Dashboards, PostHog dashboards,
  Mercury home, Better Stack monitors.

## 7. Governance (as tests)

- G1. A board can only reference registered module ids; an unknown id renders the grey frame.
- G2. (checked by a test that lists `git diff --name-status origin/main...HEAD` and greps added
  lines) The diff adds no write path absent from the baseline: no new file under `app/api/`, no new
  exported `POST`/`PUT`/`PATCH`/`DELETE` handler, no new `create table` in `supabase/` or
  `mesh/schema/`. Every non-GET request reachable from a board is one that the same panel already
  makes on `main` (§4.1 action column), through the same route.
- G3. `lib/boards/**` and `components/boards/**` contain no `fetch` with a `method` option and
  no string `"POST"`, `"PUT"`, `"PATCH"`, `"DELETE"`.
- G4. Registry discovery: every module has ≥ 1 source from §3.3, ≥ 1 view, a min size; every view
  renders each of the five states through `ModuleFrame` (each mocked).

## 8. Repo gates the diff must clear

- New files under `dashboard/components/` → a new entry in `.github/smoke-surfaces.json`
  (or a `Surface-Allow:` trailer). Logic prefers `lib/boards/`.
- Anything touching `/api/pi-ceo` goes through `lib/pi-ceo-fetch.ts` (`proxy_fallback_lint.py`).
- New page registered as surface **MC-20** everywhere the MC list is enumerated:
  `scripts/mission_control_register.py`, `scripts/mission_control_scorecard.py`,
  `docs/plans/mission-control/coverage-register.md`, `dashboard/e2e-live/surfaces.ts`,
  `dashboard/e2e-live/panel-coverage.json`.
- File length ≤ 300 lines for every new `.py/.ts/.tsx` in the diff (registry, components, tests), functions ≤ 40 lines for new Python
  (`file_length_lint.py`, `function_length_lint.py`, run after `git add`).
- Existing tests stay green; tests that stub `fetch` per case rely on the global `resetSources()`.
  The brief names these as the ones most likely to need a poller-aware change, and each keeps its
  assertions: `fleet-tile.test.tsx` (per-case stubs → reset), `control-telemetry-refresh.test.tsx`
  (30 s fake timer → the shared poller must use the same timers and the same 10 s abort),
  `operator-readiness.test.tsx` (15 s fake timer → `pi-health`/`sessions` at 15 s),
  `kill-switch-panel.test.tsx` (status shapes → kill-switch reader), and
  `e2e-writes/kill-switch.spec.ts` (Playwright write journey → unchanged routes).
- `e2e-live/panel-coverage.json` keeps listing each converted panel at its module path. The panels
  stay where they are (`components/control/*`, `components/wall/*`); only their data hook moves, so
  the existing entries remain correct and MC-20 gets its own list.

## 9. Acceptance

Each A-test is shown **failing on a control arm first** (the same test against `main`, or against
the build with the guarded behaviour removed), then passing. Receipts go in the handoff.

| # | Test | Tool |
|---|---|---|
| A1 | On `/control/boards`: drag one module, resize one, add one from the library, remove one, switch one view; reload; all five changes persist | Playwright |
| A2 | A board with two Fleet modules makes exactly one `/api/mesh-fleet` request per interval; a board with two provider-usage modules makes exactly one provider-usage request per 30 s (through the tap) | vitest (fake timers) + Playwright request count |
| A3 | Pi-CEO backend down: every `/api/pi-ceo/*` GET answers the proxy's 200 fallback with `X-Upstream-Status: 502`; `mesh-fleet`/`model-fabric` answer 503; `swarm-status`, `kill-switch` and `curator` answer their quiet-failure bodies; `wall` answers `fleet.status:"broken"`. Every module on those feeds shows unreachable or stale. Read-only modules render no view. Each action module (ideas, health, swarm, kill switch) is asserted to render no digit inside its panel body, and the kill switch still offers "Halt swarm". `provider-usage` and `wiki-graph` are routed their 200 success shapes, because their routes build from dashboard-side data first (`provider-usage/route.ts`; `wiki-graph/route.ts` reads Supabase before the backend), and those two modules stay live | vitest + Playwright with routed responses |
| A4 | A board with an unknown module id renders the grey frame; the page does not crash | vitest + Playwright |
| A5 | Kill switch module with `/api/kill-switch` answering 401: kill control disabled, reason shown — asserted both on a board and on `/control/swarm` (where the panel also lives). Existing kill-switch tests stay green | vitest |
| A6 | Every existing page unchanged. Screenshot-gated, every page listed: `/control`; `/control/goal`, `/control/swarm`, `/control/model`, `/control/health`, `/control/roles`, `/control/build`, `/control/runs`, `/control/curator`, `/control/margot`, `/control/pipeline`, `/control/terminal`; `/loop`; `/overview`; `/command-centre`, `/command-centre/hermes`, `/command-centre/knowledge`, `/command-centre/providers`, `/command-centre/wall`, `/command-centre/wiki-graph`, `/command-centre/youtube-intent`. Before (`main`) and after (branch) Playwright screenshots of each with identical routed responses, compared with `toHaveScreenshot` at zero tolerance; masks are bounding boxes over live clocks and relative "Xs ago" labels only, and those nodes are separately asserted present in the DOM. Plus: the existing vitest suites for each converted panel stay green with their assertions unmodified; e2e green. The one intended difference (D5 signed-out kill switch) only appears under a 401, which the routed responses do not produce | vitest, Playwright |
| A7 | At 400 px wide: no horizontal page scroll; modules stack in one column | Playwright |
| A8 | `npx tsc --noEmit`, `npm run build`, `bash scripts/handoff-loop.sh` pass; the release-gate receipt records exactly `bash scripts/handoff-loop.sh` | shell |
| A9 | Write action inside a board: on a board, the Kill switch module's "Halt swarm" opens the existing confirm modal; with the POST answering 200, the modal closes and the module shows HALTED from the immediate refresh read (exactly one extra status GET after the POST, no second timer) | vitest |
| A10 | Kiosk: `/control/boards/kiosk?board=wall-1&machine=Phill_Desktop` renders the preset full-screen with no edit controls and passes `Phill_Desktop` to the wall fleet view as its own host; `?board=nope` shows an error naming the valid preset ids | vitest + Playwright |

Unit and governance tests (all gate Done):

| # | Test |
|---|---|
| T1 | One unit test per feed reader in §3.3, covering each listed success / unreachable / no_source shape and the timestamp |
| T2 | Poller contract: first subscriber starts, last unsubscribe stops; in-flight tick skipped; 10 s abort counts as a failed read; `refresh()` makes one read and no second timer; `resetSources()` clears all; stale after `3 × interval` |
| T3 | Every preset in `lib/boards/presets/` validates: registered modules and views, layout ids match items, sizes ≥ min |
| T4 | Board validation and BoardStore: invalid JSON or shape rejected with a message and storage left unchanged; unknown view falls back to the first view; storage that throws falls back to presets; export → import round-trips |
| T5 | Look rules: the `static` North Star text names its source file in the module's source line; no hex literal and no literal data array under `components/boards/` and `lib/boards/`; `ModuleFrame` title has no `uppercase` class; no net-new `lucide-react` import (the existing design-md lint) |
| T6 | MC-20 is present in every enumerated MC list: `scripts/mission_control_register.py`, `scripts/mission_control_scorecard.py`, `docs/plans/mission-control/coverage-register.md`, `dashboard/e2e-live/surfaces.ts`, `dashboard/e2e-live/panel-coverage.json` |
| T7 | Request-sharing tap: installed only by the `/control/boards` and kiosk pages (a grep test finds `installFetchTap` imported nowhere else); two provider-usage modules plus the shared source make exactly one network GET per 30 s; two wiki-graph modules make one per 300 s; a GET or POST to any other path reaches the original `fetch` with the same arguments; unmount restores the original `fetch` |
| T8 | In-board fidelity: for each view #1 panel, the panel's inner markup rendered inside `ModuleFrame` in the `live` state equals the panel rendered alone, given the same responses |

## 10. Out of scope

- Server-side board storage (table, route, sync between machines).
- Editing `ProviderUsageCockpit`, `WikiGraphTile`, `Wall.tsx`, or any `/command-centre` page.
- Making `/control` default to a board.
- New backend endpoints, new data, any new write action.
- A paid Mobbin reference pull; final visual direction beyond the four looks.
- Migrating `/overview`'s `useOperatorObservations` beyond reading the shared `pi-health` and
  `sessions` sources at its current 15 s.

## 11. Open founder decisions

1. Server-side board storage — needed for the kiosk to show a board edited on another machine.
2. Making Desk the `/control` default once Level-1 read journeys pass.
