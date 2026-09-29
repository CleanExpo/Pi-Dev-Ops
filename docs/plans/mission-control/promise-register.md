# Mission Control — Customer Promise Register (MC-PROMISE)

**Status:** DRAFT, 29 Sept 2026. Inspected revision: branch `claude/nifty-mayer-qemzix` at `6d199ffc`.
**Layer:** MC track instance of the packet's CP-02 ([adoption.md §5](../nexus-release-harness/adoption.md)).
**Rule (packet intent §4):** every advertised capability needs a working journey, support and
current evidence. For Mission Control the "customer" is the founder, and every nav blurb and
button label is a promise to him.

**Result today: 0 of 33 promises are proven.** No browser or live receipt exists for any of them
(WP-02 is blocked on `DASHBOARD_PASSWORD`, RA-7832). 20 have a mocked component test (3 of those cover
authorisation only), and 13 have code only. This register lists what must be proven; it does not claim anything works.

**How it was built:** the nav text comes from `dashboard/lib/control/nav.ts`. Button and link
labels were extracted mechanically from every `<button>`, `<a>` and `<Link>` in
`dashboard/components/control/*.tsx`, then read by hand. Labels that make no claim (Cancel, Close,
Back, show/hide toggles) are left out. Test coverage was found by searching `dashboard/__tests__/`
for each label. Line numbers rot: re-find each one with `grep -n`.

Evidence column: **Mocked** = a vitest test with a stubbed backend; **Code only** = no test found
by label or component name. "Proving journey" is the browser check WP-06/07 must run.

## A. What each screen says it is for (nav blurbs)

| # | Screen | Promise (verbatim) | Source | Proving journey | Evidence |
|---|---|---|---|---|---|
| P01 | Live `/control` | "Watch sessions after a ticket is Ready for Pi-Dev with pi-dev:autonomous." | `lib/control/nav.ts:39` | Label a test ticket, confirm the session appears. **Depends on the poller being on in production — unconfirmed (RA-7813)** | Code only |
| P02 | Goal | "Create a project brief. State the goal. Review drafts. Write to Linear." | `nav.ts:48` | Brief → analyse → review → write; ticket exists in Linear (preview only, WP-07) | Mocked (`goal-ticket-form`, `goal-project-picker`) |
| P03 | Swarm | "Watch PRs after pickup. Kill lives here." | `nav.ts:55` | PR list renders; Halt/Resume visible even when swarm status fails (`SwarmPanel.tsx:161`) | Mocked auth only (`kill-switch-auth`) |
| P04 | Models | "Governed routing and provider health." | `nav.ts:62` | Real provider states; a 500 shows as an error, not "DISABLED" | Mocked (`model-fabric-panel`) |
| P05 | Health | "Pi-SEO scores — same family as sidebar Portfolio." | `nav.ts:69` | Scores match the sidebar Portfolio source | Code only |
| P06 | Roles | "Eight-phase roster." | `nav.ts:76` | Exactly eight phases render from live data | Code only |
| P07 | Build | "Start a session from a repo URL and a brief." | `nav.ts:83` | Start on preview; log stream opens (`build-launch` test exists) | Mocked (`build-launch`, `fix-session-live`) |
| P08 | Runs | "Cron outcomes — same list as sidebar Routines." | `nav.ts:90` | Same rows as sidebar Routines | Mocked (`routine-table`) |
| P09 | Curator | "Pending curator proposals." | `nav.ts:97` | Real proposals, or an honest empty/error | Mocked (`curator-proposals-panel`) |
| P10 | Margot | "Dry-run matrix and packets." | `nav.ts:104` | Matrix and packets load through the proxy | Mocked (`margot-assets-panel`) |
| P11 | Pipeline | "Machine spec pipeline status." | `nav.ts:111` | Live pipeline list; outage shown as error | Mocked (`spec-pipeline-panel`) |
| P12 | Terminal | "Live redacted tmux panes." | `nav.ts:118` | Panes stream; a planted secret is redacted | Mocked (`terminal-panel`) |

## B. What each button says it does (write actions)

| # | Screen | Label | Source | What must be observed | Evidence |
|---|---|---|---|---|---|
| P13 | Goal | "Create brief" | `components/control/GoalProjectPicker.tsx:209` | Brief saved, survives reload | Mocked |
| P14 | Goal | "Save brief" | `GoalProjectPicker.tsx:267` | Edit persists after reload | Mocked |
| P15 | Goal | "Hide brief — Linear tickets stay" | `GoalProjectPicker.tsx:221` | Brief hidden **and** its Linear tickets untouched | Code only |
| P16 | Goal | "Try again" | `GoalProjectPicker.tsx:285` | Retries the failed load | Mocked |
| P17 | Goal | "Analyze goal" | `GoalTicketForm.tsx:247` | Drafts appear; failure shows an error | Mocked |
| P18 | Goal | "Write to Linear" / "Write the rest" | `GoalDraftReview.tsx:178` | Tickets exist in Linear; partial failure leaves "the rest" accurate | Mocked |
| P19 | Goal | "Discard" | `GoalDraftReview.tsx:189` | Drafts gone; nothing written to Linear | Code only |
| P20 | Goal | "Write the next goal" | `GoalTicketForm.tsx:288` | Form resets for a new goal | Code only |
| P21 | Live | "Drop idea" | `IdeaPipelinePanel.tsx:145` | Idea packet created | Mocked (`idea-pipeline-panel`) |
| P22 | Live | "GO" → "GO recorded. Nothing has started." | `IdeaPipelinePanel.tsx:215`, `:107` | GO recorded **and no build starts** (label is honest today — break A, RA-7811) | Mocked (`idea-pipeline-panel`) |
| P23 | Swarm | "Halt swarm" | `KillSwitchPanel.tsx:99`, `:288` | Swarm halted; state visible; confirm step shown | Mocked auth only |
| P24 | Swarm | "Resume swarm" | `KillSwitchPanel.tsx:113`, `:394` | Swarm resumes; state visible | Mocked auth only |
| P25 | Health | "▶ Fix with Claude" | `HealthGrid.tsx:419` | Session spawns; live log link (surface-treatment rule) | Code only |
| P26 | Health | "Fix next ↗" | `HealthGrid.tsx:677` | Opens the next fix | Code only |
| P27 | Build | "▶ run" / "■ stop" | `BuildForm.tsx:176` | Session starts / stops; log stream | Mocked (`build-launch`) |
| P28 | Margot | "Preview prompt" | `MargotAssetsPanel.tsx:209` | Preview renders, or an error | Mocked |
| P29 | Margot | "Build full packet (N)" | `MargotAssetsPanel.tsx:225` | Packet built with N items; progress shown | Code only |
| P30 | Pipeline | "Run pipeline" | `SpecPipelinePanel.tsx:204` | Pipeline starts; status updates | Code only (panel tested for load/error, not run) |
| P31 | Pipeline | "Refresh" | `SpecPipelinePanel.tsx:170` | List reloads | Code only |
| P32 | Pipeline | "Copy id" → "Copied" | `SpecPipelinePanel.tsx:222` | Clipboard holds the id | Code only |
| P33 | Shell | "Pick an active project" | `ProjectSelector.tsx:109` | Selection filters the screens | Code only |

## C. What this register already shows

- **Honest labels worth keeping.** P22 says plainly that GO starts nothing, which matches the code
  (break A). P15 promises that hiding a brief leaves Linear tickets alone, so the journey must
  assert both halves.
- **Promises that depend on something outside the screen.** P01 needs the production poller
  (RA-7813). P02/P18 write to the real Linear workspace, so they are preview-only and a FOUNDER
  item under WP-07. P25 and P27 spawn paid sessions, so they are preview-only.
- **Untested destructive or spawning actions:** P19, P23/P24 beyond auth, P25, P29, P30. These are
  the first write journeys to add once WP-02 unblocks.
- **Label-honesty check (MC check 12).** Every row in section B is an input to that check: the
  recorded network calls must match the label.

## D. Keeping it current

A new nav entry or write button without a row here is a gap. Re-run the extraction and diff it
against this table before each release candidate (P-PROMISE of the next MC release).
