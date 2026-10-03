# Modular Mission Control boards — spec

**Ticket:** RA-7898 · **Branch:** `feature/RA-7898-modular-boards` · **Base:** `main` @ `e3dff5e`
**App:** `dashboard/` (Next 16, React 19, Tailwind 4, zustand) · **Layout library:** `react-grid-layout@2.2.4`

## Review record

| Round | Spec revision | Reviewer model | Axes | Verdict | Blocking findings |
|---|---|---|---|---|---|
| — | — | — | — | not yet run | — |

## 1. Outcome

The founder can open `/control/boards`, see a board of modules, and — after pressing **Customize** —
move, resize, add (from a library grouped by sector), remove and re-skin modules, and switch each
module between several visuals ("views"). Boards survive reload. A wall screen can open a board
full-screen at `/control/boards/kiosk?board=<preset>&machine=<host>`.

Done means: acceptance tests A1–A8 (§9) each shown failing on a control arm and passing on the
build, plus `npx tsc --noEmit`, `npm run build` and `bash scripts/handoff-loop.sh` green.

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
  existing write succeeds (kill / resume, idea dispose, build). It does not start a second timer.
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

Stale age for every feed = `3 × interval` (minimum 15 s).

A module's state is the worst of its sources, in the order
`unreachable > no_source > stale > loading > live`.

### 3.3 Feeds, intervals and failure readers

One interval per feed. "Today" lists the rates found on `main` @ `e3dff5e`.

| Feed id | URL | Interval | Today | Reason for the chosen interval |
|---|---|---|---|---|
| `mesh-fleet` | `/api/mesh-fleet` | 20 s | 20 s (FleetTile) | Heartbeats land every few minutes; 20 s is what FleetTile already uses |
| `wall` | `/api/mesh-fleet/wall` | 5 s | 5 s (Wall) | The wall marks a snapshot stale at 15 s; slower polling would flap |
| `model-fabric` | `/api/model-fabric` | 15 s | 15 s | Unchanged |
| `swarm-status` | `/api/swarm-status` | 30 s | 30 s | Unchanged; `control-telemetry-refresh.test.tsx` pins 30 s |
| `kill-switch` | `/api/kill-switch?op=status` | 10 s | 10 s | Safety control: keep the fastest existing rate |
| `provider-usage` | `/api/command-centre/provider-usage` | 30 s | 30 s | Unchanged |
| `wiki-graph` | `/api/command-centre/wiki-graph` | 300 s | once on mount | Counts change on a sync, not minute to minute |
| `curator` | `/api/curator-proposals?status=pending&limit=10` | 30 s | 30 s | Unchanged |
| `pi-health` | `/api/pi-ceo/health` (via `fetchProxy`) | 15 s | 15 s (overview) | Unchanged; `operator-readiness.test.tsx` pins 15 s |
| `sessions` | `/api/pi-ceo/api/sessions` (via `fetchProxy`) | 15 s | 4 s / 5 s / 15 s | The overview rate; see exception E1 |
| `projects-health` | `/api/pi-ceo/api/projects/health` (via `fetchProxy`) | 30 s | 30 s and 60 s | Scan scores move hourly; 30 s keeps PortfolioFocus's rate |
| `mc-live` | `/api/pi-ceo/api/mission-control/live` (via `fetchProxy`) | 5 s | 5 s and 30 s | The live feed's "live" label means a read in the last 15 s |
| `idea-pipeline` | `/api/pi-ceo/api/idea-pipeline` (via `fetchProxy`) | 60 s | on mount + after actions | Ideas arrive by hand; `refresh()` covers the after-action read |
| `pipelines` | `/api/pi-ceo/api/pipelines` (via `fetchProxy`) | 30 s | 30 s | Unchanged |
| `local-clock` | none (browser clock) | 1 s, local | — | A clock is not a feed; always `live` |
| `static` | none (text in the bundle) | — | — | Always `live`; the text cites its file |

**Exception E1.** `FixSessionLive` in `HealthGrid.tsx` keeps its own 4 s `/api/sessions` poll. It
is a per-build fallback beside an EventSource, started only after the founder presses "Fix with
Claude", not a board feed. Out of scope here (§10).

Failure readers — one per feed, each with a unit test (§9 T1):

| Feed | Success | Read as `unreachable` | Read as `no_source` | Server timestamp |
|---|---|---|---|---|
| `mesh-fleet` | 200 `{status:"ok"}` | 503 `{status:"unavailable"}` with reason "upstream unreachable" / "machines source failed" / "fleet snapshot missing"; network error; any other non-200 | 503 with reason "mesh secret not configured" or "Pi-CEO URL not configured" | `checkedAt` |
| `wall` | 200, `fleet.status:"ok"` | 200 `fleet.status:"broken"`; non-200; network | 200 `fleet.status:"no_source"` | `generated_at` |
| `model-fabric` | 200 | 503 (any body); other non-200; network | — | none (browser time) |
| `swarm-status` | 200 with `state` ≠ `"UNKNOWN"` | 200 `state:"UNKNOWN"` (the route's own fallback); non-200; network | — | none |
| `kill-switch` | 200 with no `error` | 200 with `error` other than "not configured"; 401 (reason "signed out"); other non-200; network | 200 `error` containing "not configured" | none |
| `provider-usage` | 200 | 500; non-200; network | — | `generatedAt` |
| `wiki-graph` | 200 with `source` ≠ `"unconfigured"` | non-200; network | 200 `source:"unconfigured"` | none (`lastSync` is shown, not used for freshness) |
| `curator` | 200 with no `error` | 200 with `error` other than "not configured"; non-200; network | 200 `error` containing "not configured" | none |
| `pi-health`, `sessions`, `projects-health`, `mc-live`, `idea-pipeline`, `pipelines` | `fetchProxy` returns `ok:true` | `fetchProxy` returns `ok:false` for any reason (proxy fallback with `X-Upstream-Status`, non-200, network); `mc-live` also when the body has `error` | — | `mc-live`: `ts`; others none |

Where the server sends no timestamp, the freshness chip reads "fetched Xs ago (browser time)".
Unknown stays unknown: no fallback numbers, no sample rows, ever.

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
Remove), the freshness chip and the five states. A view component renders **only** when the
module state is `live`; the frame owns every other state. No view re-implements them.

### 4.1 Module list

| Id | Name | Sector | Sources | Action | View #1 (existing panel, unchanged) | Second views |
|---|---|---|---|---|---|---|
| `fleet` | Fleet | Machines | `mesh-fleet` | no | `FleetTile` | Heartbeat strip, Compact list |
| `wall-fleet` | Fleet board | Machines | `wall` | no | `FleetTiles` (wall) | — |
| `ship-chain` | Ship chain | Delivery | `wall` | no | `StationAccordion` (wall) | Station row, Ring |
| `wall-banner` | Attention banner | Founder | `wall` | no | `WallBanner` (wall) | — |
| `activity` | Live activity | Delivery | `mc-live` | no | `LiveActivityFeed` | Timeline, Pulse |
| `ideas` | Ideas | Delivery | `idea-pipeline` | **yes** | `IdeaPipelinePanel` | Funnel, Inbox |
| `portfolio` | Business health | Businesses | `projects-health`, `mc-live`, `pipelines` | no | `PortfolioFocus` | Bars, Tiles, Ranked list |
| `health` | Project health | Businesses | `projects-health` | **yes** | `HealthGrid` | — |
| `builds` | Builds | Delivery | `sessions` | no | (new) Board by stage | Table, Big number |
| `swarm` | Swarm | Safety | `swarm-status`, `kill-switch` | **yes** | `SwarmPanel` | — |
| `kill-switch` | Kill switch | Safety | `kill-switch` | **yes** | `KillSwitchPanel` | Status light, Detail |
| `models` | Model routing | Compute | `model-fabric` | no | `ModelFabricPanel` | Bars, Ring, Table |
| `provider-usage` | Provider usage | Compute | `provider-usage` | no | `ProviderUsageCockpit` (wrapped, unedited) | — |
| `curator` | Curator proposals | Knowledge | `curator` | no | `CuratorProposalsPanel` | — |
| `wiki-graph` | Wiki graph | Knowledge | `wiki-graph` | no | `WikiGraphTile` (wrapped, unedited) | — |
| `north-star` | North Star | Founder | `static` | no | (new) Full | Short |
| `clock` | Brisbane time | Utility | `local-clock` | no | (new) Digital | Analog |

"Unchanged" means: on `/control`, `/control/<section>`, `/loop` and `/command-centre/*` each panel
renders identically before and after, given the same responses; inside a board it renders the
same markup inside the frame. Each converted panel reads its data from `useSource` instead of its
own `setInterval`; its markup, copy and classes do not change.

`ProviderUsageCockpit` and `WikiGraphTile` are provenance-baselined
(`__tests__/command-centre-readonly.test.ts`) and are not edited. Their modules wrap them from
outside; the frame's state comes from the shared `provider-usage` / `wiki-graph` sources. Declared
delta D1: while one of these two modules is on a board, its feed is read twice per interval (the
component's own poll plus the shared one).

The `Wall` component (`components/wall/Wall.tsx`) and `/command-centre/wall` are not edited and
keep their own 5 s poll. Board modules on the `wall` feed use the shared source. Declared delta D2:
a board with wall modules open beside `/command-centre/wall` in the same browser makes two wall
reads per 5 s, one per page.

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
  (`control-subpages.test.ts` asserts exactly 11). Own nav link in `ControlSubnav`.
- **Locked by default.** "Customize" unlocks: drag (handle = card title), resize (corner handle),
  add from a library drawer grouped by sector (pick a view to add), remove, view chips under each
  card. Also: board tabs, "+ Board", "Reset to preset", export/import JSON.
- **Kiosk** `/control/boards/kiosk?board=<preset>&machine=<host>` — full-screen, Wall look, locked,
  no edit controls. Resolves **repo presets only** until server storage exists; an unknown preset
  shows an error naming the valid ids. `machine` is passed to the wall fleet view as the kiosk's
  own host. Not under `/command-centre`; `/command-centre/wall` untouched.

## 6. Looks

Built last. Matches the prototype's second version.

- **Card anatomy:** small uppercase kicker "<sector> · <status>" with a status dot; sentence-case
  title; one ⋯ menu holding "Show as" (views), the source, and Remove. No per-card footer, no
  dropdown boxes, no uppercase titles.
- **Colour:** one data accent per look; green / amber / red only where something needs attention;
  grey hollow for "no source yet".
- **Board header:** greeting with a one-line summary, quick-action chips (links to existing pages
  only), a single "Updated Xs ago", board tabs, "Customize".
- **Looks** as token overrides on the board root (`data-board-skin`): **Paper** (default desk: warm
  paper ground, white cards, indigo accent), **Graphite** (Linear-style near-black), **Slate**
  (Mercury-style soft indigo-grey), **Wall** (Graphite, larger type). One token set in
  `app/globals.css`. Root `DESIGN.md` and `.claude/DESIGN.md` record the four looks; CI lints the
  latter. No net-new `lucide-react` imports.
- Hex literals are banned in new view files; converted view #1 files keep theirs.
- Pattern references (no paid Mobbin pull in this pass): Linear Dashboards, PostHog dashboards,
  Mercury home, Better Stack monitors.

## 7. Governance (as tests)

- G1. A board can only reference registered module ids; an unknown id renders the grey frame.
- G2. The diff adds no write path absent from the baseline: no new file under `app/api/`, no new
  exported `POST`/`PUT`/`PATCH`/`DELETE` handler, no new `create table` in `supabase/` or
  `mesh/schema/`. Every non-GET request reachable from a board is one that the same panel already
  makes on `main` (§4.1 action column), through the same route.
- G3. `lib/boards/**` contains no `fetch` with a `method` option and no string `"POST"`,
  `"PUT"`, `"PATCH"`, `"DELETE"`.
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
- File length ≤ 300 lines for new `.py/.ts/.tsx`, functions ≤ 40 lines for new Python
  (`file_length_lint.py`, `function_length_lint.py`, run after `git add`).
- Existing tests stay green; tests that stub `fetch` per case rely on the global `resetSources()`.

## 9. Acceptance

Each A-test is shown **failing on a control arm first** (the same test against `main`, or against
the build with the guarded behaviour removed), then passing. Receipts go in the handoff.

| # | Test | Tool |
|---|---|---|
| A1 | On `/control/boards`: drag one module, resize one, add one from the library, remove one, switch one view; reload; all five changes persist | Playwright |
| A2 | A board with two Fleet modules makes exactly one `/api/mesh-fleet` request per interval | vitest (fake timers) + Playwright request count |
| A3 | Pi-CEO backend down (proxy answers with `X-Upstream-Status`): every backend-dependent module shows unreachable or stale and no number; provider-usage and wiki-graph stay live | vitest + Playwright with routed responses |
| A4 | A board with an unknown module id renders the grey frame; the page does not crash | vitest + Playwright |
| A5 | Kill switch module with `/api/kill-switch` answering 401: kill control disabled, reason shown. Existing kill-switch tests stay green | vitest |
| A6 | `/control`, `/overview`, `/command-centre/*` and the wall unchanged: vitest + e2e green; before/after screenshots | vitest, Playwright |
| A7 | At 400 px wide: no horizontal page scroll; modules stack in one column | Playwright |
| A8 | `npx tsc --noEmit`, `npm run build`, `bash scripts/handoff-loop.sh` pass; the release-gate receipt records exactly `bash scripts/handoff-loop.sh` | shell |

Plus: T1 one unit test per feed reader (§3.3); G1–G4 (§7).

## 10. Out of scope

- Server-side board storage (table, route, sync between machines).
- Editing `ProviderUsageCockpit`, `WikiGraphTile`, `Wall.tsx`, or any `/command-centre` page.
- Making `/control` default to a board.
- `FixSessionLive`'s own 4 s poll (E1).
- New backend endpoints, new data, any new write action.
- A paid Mobbin reference pull; final visual direction beyond the four looks.
- Migrating `/overview`'s `useOperatorObservations` beyond reading the shared `pi-health` and
  `sessions` sources at its current 15 s.

## 11. Open founder decisions

1. Server-side board storage — needed for the kiosk to show a board edited on another machine.
2. Making Desk the `/control` default once Level-1 read journeys pass.
