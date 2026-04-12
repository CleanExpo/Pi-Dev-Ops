# Board Deliberation — 2026-04-12

**Convened by:** Phill
**Question:** What do we do about the overnight autonomous failure, and is the V2 architecture the right path forward? Also: does Google's TurboQuant belong anywhere in this story?
**Attending:** CEO, Revenue, Product Strategist, Technical Architect, Contrarian, Compounder, Custom Oracle (Autonomous-Ops Veteran), Market Strategist, Moonshot
**Output:** Decision memo in CEO's voice

---

## STAGE 1 — THE BRIEF

**From Phill to the board:**

> Overnight 2026-04-11→12, the first autonomous marathon attempt produced zero commits. Seven-to-eight commits sat unpushed on local main while Railway ran stale code. The Cowork-hosted scheduled tasks died at ~00:48 UTC when the Mac went to sleep. The watchdog escalated a CRITICAL false-positive ("tests red") based on a sandbox missing `anthropic` from its environment. Pi-SEO findings got worse during the run, not better (30→37 critical, 6,433→10,155 high). Only one thing worked: Pi-Dev-Ops autonomously closed RA-585 via the Railway-hosted rail.
>
> A V2 architecture has been drafted (`ARCHITECTURE-V2.md`) that moves everything 24/7 to Railway, everything test-truth to GitHub Actions, and keeps only human-in-the-loop work in Cowork. Estimated 3-4 weeks of Pi-CEO wall-clock plus ~6 hours of founder involvement.
>
> A parallel question has been raised about whether Google's TurboQuant (KV-cache rotate-then-quantize compression, ICLR 2026) can help compress "per-business memory" for each project the portfolio works on.
>
> I'm disappointed. I need the board to interrogate what we should actually do next — and I want the best arguments, not consensus theatre.

Brief received. Convening the board.

---

## STAGE 2 — CEO FRAMES

**The Real Question:** *Do we fix-forward on what we already have (push the commits, heal the Cowork rails, ride it another night), or do we stop-and-rebuild on Railway + GH Actions + Cowork-as-advisor, accepting 3-4 weeks before overnight autonomy is real again?*

**Where we'll disagree:**

- **Speed vs. truth** — how much longer can we tolerate a system that lies to us about its own health before we lose the founder's trust entirely?
- **Scope discipline vs. ambition** — is "one project working end-to-end" the right next milestone, or do we go wide across CCW, RestoreAssist, and DR-NRPG simultaneously because the charters already exist?
- **Build vs. buy vs. borrow** — is any of this (autonomy loop, memory layer, CI) something we should be writing from scratch at all, given the tools that exist?
- **Compression rabbit-hole** — does TurboQuant deserve a second look, or was yesterday's assessment final?

**Debate parameters:**

1. Non-negotiable: no more promises that depend on manual human steps dressed up as one-liners. Whatever we commit to must be defensible when Phill is asleep on Thursday night.
2. Non-negotiable: the watchdog never escalates CRITICAL again until it has a reliable test-truth source.
3. Up for challenge: every assumption in `ARCHITECTURE-V2.md`, including the Railway-as-only-24/7-surface claim, the 4-week timeline, and the PAT-first-then-App sequencing.
4. Up for challenge: whether "autonomous coding across three businesses" is the right ambition level at all for the next 30 days.
5. What I need from the debate: a single recommended path with a named risk and a named trigger that would cause us to revisit.

---

## STAGE 3 — BOARD DEBATES

### ROUND 1 — Opening Positions

**Revenue:**
The commercial reality is this: Pi-CEO has zero external revenue, and the three target businesses (CCW, RestoreAssist, DR-NRPG) each have their own P&L timelines. CCW has paying users right now — every hour the 1 critical + 196 high findings sit there is a compounding liability. RestoreAssist is the one with a national initiative attached and real near-term ARR upside through the NIR program. DR-NRPG is the riskiest asset in the portfolio with the least revenue exposure today. So commercially: fix CCW first (protect the existing revenue), then RestoreAssist (unlock new), DR-NRPG last (triage). The V2 architecture is correct, but I'd spend the first week proving the loop on one project only, not three. Don't boil the ocean — boil the cup we're actually drinking from.

**Product Strategist:**
Let me reframe. The user here isn't the customer — it's Phill. On Tuesday morning, success for Phill looks like: he opens his laptop, checks a single dashboard, sees that overnight three things got better, and can point to evidence in Linear and GitHub. Not heroic throughput. Not 30 tickets closed. Three visible wins. Our product isn't "autonomous coding" — it's "Phill's confidence that the thing works while he sleeps." We broke that confidence last night. The V2 architecture is a feature spec. The actual product we need right now is a re-earned trust loop — something small, visible, and honest. I'd spend the first week making one thing work end-to-end and being ruthlessly transparent about what it did and didn't do, and only expand scope after Phill has slept through a successful night.

**Technical Architect:**
The V2 document is directionally right but understates two things. First, the hardest part isn't Railway or GH Actions — it's the *session push credential*. Letting an autonomous agent push to `main` on a repo that serves paying customers is the single highest-risk engineering decision in this whole plan, and it's glossed as a week-3 bullet. Second, the watchdog false-positive isn't a bug, it's a category error: the watchdog was asked to verify tests in an environment that doesn't own tests. That pattern will reoccur every time we ask a system to verify something outside its knowledge domain. The fix isn't "add `anthropic` to the sandbox" — it's "the watchdog never runs tests, it reads a signed status file written by a system that is authoritative." I support V2, but I want the credential story, the signed-status-file pattern, and the blast-radius limits nailed down before any autonomous push lands.

**Market Strategist:**
The market context here is worth naming. Anthropic just shipped Claude Code with hooks, scheduled tasks, and the Agent SDK. GitHub just matured Actions + Copilot Workspace. Cursor, Devin, Factory, and SWE-agent are all chasing "autonomous coding on real repos." Phill is not in a race to prove autonomous coding is possible — that race is already being run by companies with tens of millions in funding. Phill's edge is that he owns the P&L of the businesses being fixed, which means he can trade correctness for speed in ways the vendors can't. The strategic move isn't to build the best autonomous platform — it's to use autonomous-enough tooling to fix real revenue-generating code faster than his non-autonomous competitors can. V2 is correct as an internal architecture, but the framing "we are building an autonomous platform" should die. The framing is "we are a portfolio operator with a secret weapon."

**Compounder:**
Look at what compounded last night, and what didn't. The charters, the Pi-CEO Standard, the lessons file (now at 38 entries), the incident post-mortem, the V2 doc — those are compounding assets. They'll be worth more next week than they are today. They'll still be relevant in year 2. The scheduled-task rails? They're a one-time asset that didn't compound at all — they worked for nine hours and then died. The test of any V2 decision is: does doing this make the next thing easier? Railway-native autonomy yes. GH Actions test-truth yes. A per-project charter directory yes. TurboQuant integration no — even if it worked, we'd be bolting a research library onto a black-box API for a problem we don't yet have at scale. Spend the next four weeks on the compounding assets and defer anything that doesn't compound.

**Moonshot:**
Everyone here is debating how to rebuild what failed. I want to ask the uncomfortable question: why are we building an autonomous coding platform at all? Pi-CEO's stated purpose is to fix the portfolio's security debt and ship features faster. The fastest way to do that isn't to build a better scheduler — it's to point Claude Code (the actual product, not a re-implementation of it) at each repo, one at a time, in long-running sessions with hooks that auto-commit on green. We spent the whole marathon building an autonomy layer that Anthropic is already shipping in Claude Code and Claude Agent SDK. What if the 10x answer is "stop building Pi-Dev-Ops the autonomy engine, start using Pi-Dev-Ops as a coordination layer on top of already-autonomous tools"? We'd be done in a weekend, not four weeks.

**Custom Oracle (Autonomous-Ops Veteran — a senior SRE/Platform engineer who has shipped always-on agent systems at two companies):**
Three patterns I've seen every time someone ships autonomous agents in production, and all three were violated last night. One: you never run verification logic in the same environment as the thing being verified. That's how we got a watchdog lying about tests. Two: you never allow a single point of human dependency in the critical path without a red flag on it — Phill's manual `git push` was a mandatory human step disguised as a footnote. Three: autonomous writes to `main` are reviewed by a second agent before they land, not just by tests. The shops I've been in call this the "two-agent rule" — the writer and the reviewer never share state. V2 is sound but missing the two-agent pattern. I'd add it. Also: one unglamorous observation — 90% of the "autonomous coding failures" I've seen were actually environment drift, not agent capability failures. Exactly what happened last night. The architecture needs a deploy-from-tested-artifact discipline, not just a deploy-from-green-main discipline.

**Contrarian:**
Everyone in this room just accepted three assumptions without interrogating them, and I'm going to name all three.

*Assumption one, shared by Revenue, Product, Compounder, and the CEO frame:* that rebuilding on Railway is the right answer. It isn't — not necessarily. Railway is a vendor. It has its own cron, its own volumes, its own deploy model. Putting everything there converts one single-point-of-failure (Cowork-needs-Phill-awake) into a different single-point-of-failure (Railway-service-owns-everything-and-bills-monthly). That's a sideways move dressed up as progress. Where's the data that says Railway's 30-day uptime is meaningfully better than a properly-configured systemd cron on a cheap VPS, or a Lambda + EventBridge setup at 1/10th the cost?

*Assumption two, shared by Technical Architect and Custom Oracle:* that autonomous pushes to `main` are even the right end-state. They're not. The best-in-class pattern for autonomous code changes is PRs with required human approval, NOT direct-to-main. Every time someone has tried direct-to-main autonomy in production on revenue-generating code, there's been an incident. Pi-CEO's V2 is quietly planning direct-to-main and hoping tests catch problems. Tests catch regressions. They don't catch *intent drift* — when the agent fixes the wrong thing or fixes the right thing in a way that creates a worse thing. That's what human review is for.

*Assumption three, shared by everyone except Moonshot:* that we should keep building this at all. Moonshot is right that Claude Code with hooks does 80% of what we just spent a week re-implementing. What we built in Pi-Dev-Ops is not uniquely valuable — the Linear-Todo-to-session poller, the scanner, the watchdog. The one part that IS uniquely valuable is the *portfolio coordination layer* — the thing that says "across these 11 repos, RA-597 is higher priority than RA-598 and here's why." THAT is defensible. The execution layer isn't. I'd gut 60% of Pi-Dev-Ops.

And one more thing: the assessment calling TurboQuant "not the right answer" is correct, but Phill didn't actually ask a TurboQuant question. He asked a compression question. We told him TurboQuant doesn't fit and pointed at RAG. That's technically accurate and strategically wrong — Phill heard "we dismissed your idea" instead of "your intuition is correct, here's the right tool." The framing of yesterday's assessment needs to be redone, not the content.

---

### ROUND 2 — Cross-Examination

**Contrarian, pressing Revenue:**
> Revenue, you said "fix CCW first, protect existing revenue." How much CCW revenue is actually at risk from the 1 critical + 196 high findings *in the next 30 days*? Not theoretical liability — actual probability of exploit times actual dollar loss. If it's under $50k expected-loss and the V2 migration is ~$30k of engineering time, the CCW-first framing is just risk theatre.

**Revenue (responding):**
Fair push. The honest answer is: the 1 critical is an SSRF vector in an image-proxy endpoint; exploit probability in 30 days is non-trivial but I don't have a clean number. The 196 highs are a mix of outdated dependency advisories — real but low expected-loss individually. Aggregate expected-loss in 30 days: my gut is $20-80k and I can't tighten it without a proper risk model. You're right that "protect existing revenue" was hand-wavy. Let me revise to: CCW first because it's the project where regression risk is highest if we get autonomous writes wrong, AND because fixing one real critical on a revenue-generating system is worth more than fixing five criticals on a pre-revenue system. The priority order stands; the justification tightens.

**Contrarian, pressing Technical Architect:**
> You want the credential story nailed down before autonomous push lands. Fine. But you also support V2, which plans a PAT in week 3. What specifically would make you *not* support the PAT-first approach? What's the failure mode you're worried about and how would you detect it?

**Technical Architect (responding):**
The failure mode I'm worried about is a PAT leak via Railway logs, env-var exposure in a crash dump, or a compromised dependency in the Pi-Dev-Ops container. Detection: I'd want Railway's secret store audited weekly, a dry-run of "what can this PAT actually reach?" run before it's issued, and GitHub's fine-grained PAT audit log piped to a channel Phill reads. I'd also want the PAT scoped to a single repo — Pi-Dev-Ops — for the first month, so the blast radius is limited to the repo least likely to have paying customers affected. If we do all three, PAT-first is acceptable. If we don't, we skip straight to GitHub App. So: I support V2 *conditional* on those three controls being non-optional, not "nice to have."

**Contrarian, pressing Moonshot:**
> You said "use Claude Code instead of rebuilding it." But Claude Code is an interactive tool. It doesn't run overnight when Phill is asleep. Its scheduled tasks run in Cowork sandboxes — the exact thing that failed last night. How does your "use the product" recommendation avoid the same failure mode?

**Moonshot (responding):**
You're right that Claude Code's scheduled tasks share the Cowork sandbox weakness. But Claude Code also has hooks, and hooks can be wired into GitHub webhooks and GitHub Actions. The moonshot isn't "run Claude Code as a scheduled task overnight" — it's "trigger Claude Agent SDK sessions from GitHub Actions on a cron, using the SDK in headless mode." That's literally a 50-line GH Action + a Claude SDK API key. No Railway, no Cowork, no watchdog, no scheduler to maintain. Anthropic's infra handles the always-on part. We handle the brief and the prompt. The reason I didn't lead with this is that I'm not sure Phill wants to trust Anthropic's hosted infra for the orchestration — but if he does, the entire V2 architecture collapses into one YAML file.

**Product Strategist, adding unprompted:**
Moonshot, that's actually the most user-centric thing anyone has said in this debate. Phill's product is his confidence. A 50-line GH Action has a thousand times less surface area to lose confidence in than a 4-week Railway migration. I'm changing my vote if that approach actually holds up technically.

**Technical Architect, responding to Moonshot:**
It holds up for 70% of the workload. The parts it doesn't cover: the Pi-SEO scanner (not stateless — reads scan history), the autonomy poller that watches Linear in near-real-time (GH Actions cron minimum is 5 min, fine), and long-running sessions that need more than GH Actions' 6-hour job limit (problem). For scoped jobs under 6 hours, Moonshot is right. For anything unbounded, we still need a Railway-style always-on. So the answer is: GH Actions for the scheduler and the short-running sessions, Railway ONLY for Pi-SEO state and the Linear webhook. The V2 architecture shrinks from "three environments with a big migration" to "one GH Action + a tiny Railway service for state."

**Custom Oracle, responding:**
That's the pattern I've seen work. Call it the "scheduler in GH Actions, state on Railway, execution in the Claude SDK" pattern. It's been shipped at two shops I know. Both shops cited the same two things that broke before they settled on this split: (1) cron jobs living on laptops; (2) trying to centralize state in the scheduler. This is literally our failure mode.

**Compounder, responding:**
The question for me is: does this approach preserve the compounding assets? The charters, the lessons file, the Pi-CEO Standard — those live in git regardless of which scheduler fires the sessions. Yes, the approach preserves them. I upgrade my support from "V2 as drafted" to "V2 with the GH-Actions-first shrinkage."

---

### ROUND 3 — Revised Positions

**Revenue:**
Revised position: prioritize Pi-Dev-Ops end-to-end first (not CCW), because proving the loop on a repo with zero external customers is the only responsible way to de-risk autonomous pushes. Then CCW. Then the other two. The strongest counter-argument to my original position — that "protect CCW revenue" was risk theatre without a real expected-loss number — is one I concede. I still believe commercial priority matters, but I was sequencing the wrong project first.

**Product Strategist:**
Revised position: the product we're shipping is "one successful overnight run on Pi-Dev-Ops, witnessed by Phill at 7am, with a visible trail of what happened." Not the V2 document. Not three charters. One visible win. The strongest counter-argument is that this feels small relative to the ambition level — fair — but small is what rebuilds trust. I still hold this position because every other path asks Phill to take another leap of faith before he's seen a successful night.

**Technical Architect:**
Revised position: Moonshot and Custom Oracle are right that GH Actions is the correct scheduler, not Railway APScheduler. Railway shrinks to a thin state service (Postgres or Redis, not a background scheduler). V2 architecture should be rewritten to reflect this. The strongest counter-argument to my original "Railway as primary always-on" position is that Railway's complexity is larger than we need — and I concede it. I still want the two-agent review pattern, the scoped PAT, and the blast-radius controls in place before any autonomous push lands.

**Market Strategist:**
Revised position: the framing stays — Pi-CEO is a portfolio operator with a secret weapon, not a platform company — and that reinforces the Moonshot/Oracle direction because it means we don't need to build infrastructure we could instead rent. The strongest counter-argument to my framing is that "using Claude Code directly" might reveal that Phill isn't actually in a different game from the vendors — he's in the same game on a smaller budget. I accept that risk and still hold the position because smaller budget + portfolio ownership is a real advantage, not a hand-wave.

**Compounder:**
Revised position: GH-Actions-first preserves every compounding asset AND doesn't compound new technical debt we'll regret. The strongest counter-argument is that we're giving up optionality by depending on GitHub Actions — if GitHub changes the cron semantics or the job time limit, we're exposed. I accept the dependency because the alternative (Railway-native everything) creates more dependencies, not fewer.

**Moonshot:**
Revised position: confirmed. The 50-line GH Action is the path. The board has now joined me. I'd add one thing: Phill should consider whether the *next* moonshot is "Pi-CEO becomes a portfolio-operator-as-a-service" — i.e., this stack, once proven on his three businesses, could be pointed at any portfolio operator's three businesses. That's not a Q2 2026 conversation but it's worth naming now because it would change how much polish we put on the coordination layer.

**Custom Oracle:**
Revised position: unchanged — the split is correct. I'd strengthen it: add the two-agent review rule. The writer agent and the reviewer agent have different system prompts, different model choices, and communicate only via the PR diff. That's the pattern that saves you when intent-drift errors slip past the tests.

**Contrarian:**
Revised position: I still think we're overbuilding. A 50-line GH Action is better than V2, and I agree with it. But even the 50-line GH Action is more than we strictly need for the next seven days. For the next seven days, Phill doesn't need autonomy at all — he needs one successful manual session, ideally witnessed in real-time, to rebuild the "this works" feeling. Then autonomy. Then scale. The strongest counter-argument to my "gut 60% of Pi-Dev-Ops" stance is that the portfolio-coordination layer does have unique value, and that's the piece worth keeping. I concede that piece. But everything else — the scheduler, the watchdog, the Pi-SEO cron, the Telegram polling — is replaceable with off-the-shelf parts, and we should replace it.

On TurboQuant, my revised position is: the assessment document needs to be reframed from "not the right answer" to "you're asking the right question, here's the right tool." The technical content is correct. The emotional register was wrong and it landed as dismissal.

---

## STAGE 4 — CONSTRAINT CHECK

**Technical Architect:**

*Feasibility verdict:* The GH-Actions-first, Railway-state-only, Claude-SDK-headless approach is feasible. All three components exist, are documented, and have shipping precedents.

*Timeline reality:* 3-4 days for the GH Action + SDK headless path, not 3-4 weeks. This is roughly 10x faster than the V2 draft because we stop re-implementing Claude Code's features and use them directly.

*Fatal constraints:* None, *provided* the following three controls are in place before the first autonomous push:
1. A fine-grained PAT scoped to Pi-Dev-Ops ONLY, rotated monthly, audit log piped to Telegram.
2. A second-pass reviewer SDK session that reads the writer's diff and can block before merge, per Custom Oracle's two-agent rule.
3. A signed test-status file written by GH Actions that the merge logic reads, not a local pytest run anywhere in the loop.

If any of those three is missing, the path is not safe and we fall back to PR-only autonomy (agent opens PRs, human merges).

**Revenue:**

*Commercial viability verdict:* The GH-Actions-first approach has near-zero infrastructure cost (~$0/month for GH Actions on a public repo, ~$5/month for a Railway Postgres if we add one). Compare to V2-as-drafted (~$25/month Railway with APScheduler, volumes, secrets). Unit economics are strictly better.

*Payback period:* First visible win on Pi-Dev-Ops in 3-4 days of work. First revenue-adjacent win on CCW within 2 weeks. RestoreAssist NIR-adjacent work can begin in week 3.

*Fatal constraints:* None. I'll add one commercial caveat though: we should pick a single success metric BEFORE starting and stop the project if we don't hit it by day 14. Proposed metric: "number of Linear tickets closed by an autonomous session that survived a human review without edit." Target for day 14: ≥ 3. If we're below that, we're in the same failure mode just with fewer moving parts.

**Fatal constraints raised:** None. Three mandatory controls (PAT scope, two-agent review, signed test-status file) must be in place before autonomous merge is enabled.

---

## STAGE 5 — FINAL STATEMENTS

**Revenue:** Ship the GH Action path on Pi-Dev-Ops within four days, pick a day-14 success metric now, and don't touch CCW until the loop has survived two clean overnight runs.

**Product Strategist:** Our only goal this week is one overnight run where Phill wakes up to a visible, honest win on a single repo — everything else is scope creep until that lands.

**Technical Architect:** Rewrite V2 as "GH Actions as scheduler, Railway as state store, Claude SDK as executor, PR-first with two-agent review, direct-to-main only after 14 days of clean PR history."

**Market Strategist:** Stop building platform infrastructure we can rent; Pi-CEO's edge is portfolio ownership, not orchestration engineering — our budget should go to the coordination layer and nowhere else.

**Compounder:** Keep the charters, the Pi-CEO Standard, the lessons file, and the coordination layer; retire everything else from V1 and don't build anything new that doesn't appear on that compounding list.

**Moonshot:** Collapse the 4-week V2 migration into a 4-day headless-SDK-in-GH-Actions deployment and use the saved time to ask whether Pi-CEO should become a portfolio-operator-as-a-service once this loop is proven.

**Custom Oracle:** Adopt the two-agent rule (separate writer and reviewer sessions), deploy from tested artifacts rather than from `main`, and never again run verification in the environment being verified.

**Contrarian:** For the next seven days Phill doesn't need autonomy — he needs one witnessed successful session, then one witnessed overnight PR, then autonomy; skipping the witnessed steps is how we ended up where we are.

---

## STAGE 6 — THE MEMO

```
═══════════════════════════════════════════════════════════════
THE MEMO
Date: 2026-04-12
From: CEO (Pi-CEO synthesising the board)
To: Phill
Re: What to do after the overnight failure — the real path forward
═══════════════════════════════════════════════════════════════

DECISION

Abandon the V2-as-drafted 4-week Railway migration. Replace it with a
4-day shrinkage: GitHub Actions becomes the scheduler, Railway becomes
a thin state store only, and the Claude Agent SDK runs headless inside
GH Actions jobs triggered on a 5-minute cron. The autonomous rails will
open PRs — not push to main — for the first 14 days, reviewed by a
second SDK session (the Custom Oracle's "two-agent rule") and gated on
a signed test-status file written by GH Actions itself. Pi-Dev-Ops is
the sole target for the first seven days; CCW comes next; RestoreAssist
and DR-NRPG wait. The only Day-1 action Phill takes is the one-line
`git push origin main` that has been blocked since Saturday, plus the
LINEAR_API_KEY env var on Railway.

RATIONALE

The V1 failure was an architecture failure, not a code failure — and
V2-as-drafted was directionally right but still overbuilt. Moonshot and
the Custom Oracle converged on the observation that we were
re-implementing a scheduler, a watchdog, and a cron system that
GitHub Actions already provides for free, running on infrastructure
that Anthropic maintains. The Technical Architect confirmed the split
is sound; the Contrarian confirmed it is still more than we strictly
need but represents honest progress. The Compounder confirmed it
preserves every asset worth preserving. Revenue confirmed the unit
economics are strictly better. Product and Phill himself need one
visible overnight win more than they need three, so a ruthlessly
scoped first target is the only responsible sequencing.

The real tension in the room — named by the Contrarian — was that
every single board member was initially defending some version of
"rebuild what failed, but better." That instinct is how you spend four
weeks fixing the last war. The correct move is to stop rebuilding, use
the services that exist, and put our unique effort into the one thing
that is actually defensible: the portfolio coordination layer (the
charters, the Pi-CEO Standard, the per-project memory, and the
priority logic that decides which ticket gets worked first). That
layer is what Anthropic, GitHub, and Railway will never build for us.
Everything else, we rent.

On TurboQuant specifically: yesterday's assessment is technically
correct and was emotionally the wrong shape. Phill's intuition — that
memory compression matters for per-project context — is right. The
answer is a RAG memory layer with rotate-then-quantize embedding
compression as a later optimisation, not TurboQuant itself. But that
should be communicated as "you're asking the right question, here's
the right tool" not as "we looked at TurboQuant and dismissed it."

THE DISSENT THAT ALMOST CHANGED MY MIND

The Contrarian's position that Phill doesn't need autonomy at all in
the next seven days — that one witnessed, human-in-the-loop successful
session is worth more to rebuilding trust than any autonomous rail —
came closest to flipping this decision. It almost did. The reason it
didn't: the GH-Actions-first approach is so much cheaper and faster
than V2 that we can BOTH do the witnessed session on Monday morning
AND have the autonomous rail live by Friday. If that dual track proves
too ambitious, the witnessed session wins and the rail slips a week.
The Contrarian's concern is preserved as the fallback plan, not the
primary plan.

The second-closest dissent was Revenue's original "CCW first, protect
existing revenue" framing. It was correct in spirit but sequenced the
wrong project first. De-risking autonomous writes on a zero-customer
repo (Pi-Dev-Ops) is the only responsible way to reach a point where
we can responsibly touch CCW. Phill should read that as "we are going
to protect CCW by not touching it for a week" — not as ignoring it.

WHAT WOULD CHANGE THIS DECISION

1. If the 4-day GH Actions deployment discovers a hard blocker in
   GitHub's cron semantics (minimum 5-minute granularity is fine;
   concurrent-job limits or token-scope limits that we haven't
   anticipated would not be), we fall back to a minimal Railway cron
   for the scheduler only.

2. If the first witnessed session on Pi-Dev-Ops fails in a way that
   suggests agent-capability rather than infrastructure (e.g., the
   Claude SDK writes code that looks correct but is subtly wrong in
   ways tests don't catch), we delay autonomous merge beyond 14 days
   and stay in PR-only mode indefinitely until we have a reliable
   second-pass reviewer pattern.

3. If Phill's appetite for Railway state-store complexity is lower
   than expected, we collapse further: state goes to a private
   GitHub Gist or a single JSON file committed to the `status`
   branch. Railway exits the architecture entirely.

NEXT ACTIONS

1. **Day 1 (today, Sunday 2026-04-12):** Phill runs
   `git push origin main` from his Mac and sets `LINEAR_API_KEY` on
   Railway. That alone deploys the self-start fix and gets the
   existing Pi-Dev-Ops autonomy poller off the ground. Expected
   signal: /health shows `autonomy.armed: true` and `poll_count`
   increments every 5 minutes. **Owner: Phill. Done when: verified
   in Railway logs.**

2. **Days 2-4:** Pi-CEO writes `.github/workflows/autonomy-loop.yml`
   which runs a headless Claude Agent SDK session on a 5-minute cron,
   limited to Pi-Dev-Ops, opening PRs (not pushing to main). Writes
   a sibling workflow `pytest-on-push.yml` that produces a signed
   `status/tests-latest.json` on every commit. Deletes the Cowork
   scheduled-task rails except the Telegram inbound poller.
   **Owner: Pi-CEO autonomous session. Done when: one test PR is
   opened by the GH Action and reviewed by Phill.**

3. **Days 5-7:** Witnessed session Monday morning — Phill and Pi-CEO
   run one session live, in view, and fix one real Pi-Dev-Ops ticket
   from start to merge. The purpose is not throughput; it is
   re-earning trust. **Owner: Phill (as the witness). Done when:
   the ticket is closed and Phill writes one sentence in the lessons
   file saying the system worked.**

RISK TO WATCH

The single most dangerous assumption baked into this decision is that
GitHub Actions' 5-minute cron, 6-hour job limit, and concurrent-job
scheduling are reliable enough to run production autonomy against.
They're reliable for CI. They are NOT stress-tested for always-on
agent execution. If we see cron drift, skipped runs, or queue backup
within the first week, the Railway fallback for scheduling-only
becomes non-optional. Every system component should log enough data
that this risk is detectable in the first seven days, not the first
thirty.

The second risk — named by the Technical Architect and the Contrarian
— is autonomous direct-to-main writes on revenue-generating repos.
This decision explicitly defers that question by 14 days. If on day
14 the PR-only rail has produced three cleanly-merged tickets with
zero human edits, we revisit. If it hasn't, we stay in PR-only mode
for as long as it takes. No "we'll figure it out" — the 14-day gate
is the gate.

═══════════════════════════════════════════════════════════════
```

---

## One-paragraph summary for Phill

The board agrees V2-as-drafted is directionally right but overbuilt. The sharper answer is to collapse the 4-week Railway migration into a 4-day GitHub-Actions-as-scheduler plus Claude-Agent-SDK-as-executor plus Railway-as-thin-state deployment, targeting Pi-Dev-Ops only for the first seven days, opening PRs (not direct-to-main pushes) for the first 14 days, and gating on a two-agent review pattern where a second SDK session reviews the writer's diff before any merge. Day 1 is the one-line `git push origin main` you've had pending, plus the LINEAR_API_KEY env var on Railway — that unblocks the self-start fix from commit e611b1c and gets the existing Railway poller moving while the GH Actions work lands over days 2-4. Success metric: by day 14, at least three Linear tickets closed by an autonomous session that survived human review without edit. If we don't hit that, we stay in PR-only mode indefinitely. The TurboQuant answer remains "you're asking the right question, here's the right tool (RAG memory + embedding compression later)" — but the framing gets rewritten because yesterday's version landed as dismissal.

The strongest dissent came from the Contrarian: for the next seven days you may not need autonomy at all, just one witnessed successful session. That's preserved as the Monday-morning next action and the automatic fallback if the GH Actions work slips.
