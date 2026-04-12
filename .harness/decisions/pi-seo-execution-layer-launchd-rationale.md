# Decision — Pi-SEO Execution Layer

**Date:** 2026-04-11
**Author:** Pi-CEO board (parallel deliberation, synthesised by the orchestrator)
**Status:** Ratified. Supersedes any earlier draft that assumed Pi-SEO needed to be built from scratch on a Mac Mini.
**Related files:** `.harness/agents/pi-seo-monitor.md`, `.harness/cron-triggers.json`, `.harness/executive-summary.md`

---

## The corrected starting point

Pi-SEO already runs. The agent definition lives at `.harness/agents/pi-seo-monitor.md` and the cron schedule lives in `.harness/cron-triggers.json` with four daily triggers at 01:00, 07:00, 13:00, and 19:00 UTC. Execution currently happens on the Railway backend via the CLI entry point `python -m app.server.agents.pi_seo_monitor`. This decision does not invent a new execution layer. It reconciles the founder's stated preference (run on the Mac Mini) with the system that already exists (runs on Railway), and records why the primary execution path stays on Railway.

## The decision

**Pi-SEO continues to execute four times daily on the Railway backend as its primary run path.** The founder's Mac Mini is a secondary, optional local companion that can run an additional shell session via `launchd` once per day for manual-inspection scenarios — not a replacement for the Railway cron. The Cowork `schedule` skill is not used for either path because its failure modes are undocumented.

## Why Railway stays primary (even though the founder said "Mac Mini")

Three reasons, in order of weight.

First, Pi-SEO on Railway is shipped infrastructure. Sprint 7 closed with a ZTE score of 60 out of 60 and Pi-SEO wrote monitor digests on 2026-04-10. Rebuilding the same capability on the Mac Mini would throw away working code and reintroduce failure modes that Pi-Dev-Ops has already debugged (session crashes, rotation of logs, atomic writes to `.harness/monitor-digests/`, retry semantics under load).

Second, Railway runs continuously. The Mac Mini runs when the founder is awake or when the lid is open. The vision of a portfolio overseer that watches the business while the founder sleeps requires a host that is awake while the founder is not. Railway is that host.

Third, the founder does not need to write code to use the Railway cron. It already runs. The stated preference for Mac Mini came from a (reasonable) assumption that local infrastructure is cheaper to reason about than cloud infrastructure. That assumption is wrong in this case because the cloud infrastructure already exists.

## Why the Cowork `schedule` skill is not the primary path

The `schedule` skill's documentation does not specify where the scheduler runs (client-side in Cowork, or server-side?), what happens if Cowork is unavailable when a task should fire, or what happens when a run takes thirty minutes and the next is due in five minutes. These are not theoretical gaps. Pi-SEO's entire purpose is to produce reliable visibility; depending on infrastructure with undocumented failure modes creates a hidden fragility that contradicts the purpose.

## Why `launchd` is the right tool for the optional Mac Mini companion

If a local companion is ever added (for example, to run a ceo-board session on the founder's laptop every morning before the founder opens the dashboard), the right scheduling tool on macOS is `launchd`. Reasons: it survives reboots, survives Cowork outages, survives Claude Code session crashes, has twenty-plus years of production use on every Mac, and fires reliably even when the target user-facing app is closed. The installation cost is approximately one hour of engineering assistance once, then years of reliability. The alternative (the `schedule` skill) trades one hour of setup for ongoing ambiguity about whether runs actually fire.

## The dissent that almost flipped the decision

The Contrarian pushed hardest on the undocumented failure modes of the `schedule` skill. If Cowork published server-side resilience guarantees, queuing behaviour under load, and retry semantics on failure, the argument for the `schedule` skill would be materially stronger. The fact that those guarantees are absent created legitimate doubt. The dissent did not flip the decision because `launchd`'s durability is documented and proven whereas the `schedule` skill's durability is ambiguous. If Cowork closes that documentation gap, the decision should be revisited.

## What would change this decision

1. Cowork publishes clear documentation on the `schedule` skill's server-side resilience, queuing semantics, and failure modes. If the `schedule` skill is proven server-side resilient with queueing, the calculus shifts.
2. Railway becomes unreliable or prohibitively expensive for the Pi-SEO cron workload. Local execution then becomes a cost and reliability necessity rather than a preference.
3. Six months of production use reveals that Railway is fragile for the Pi-SEO workload in a way that Mac Mini execution would not be. Evidence required, not speculation.

## Action items that actually follow from this decision

1. **No migration to launchd is required for Sprint 8.** Pi-SEO stays on its existing Railway cron. Sprint 8 Priority 1 (activation on all ten repos) uses the existing execution path.
2. **If a local companion is later requested,** the implementation pattern is: a `.plist` file at `~/Library/LaunchAgents/com.phill.pi-seo-companion.plist` (user-scope, no `sudo` required), pointing at a shell script that invokes the Claude Code CLI with a prompt file stored next to it, writing output to a folder the founder can read in any text editor. Keeping it in `~/Library/LaunchAgents/` rather than `/Library/LaunchDaemons/` avoids the permission risk of the earlier draft memo.
3. **The Cowork `schedule` skill is not disabled.** It remains available for founder-triggered manual refreshes if that workflow ever becomes useful. It is not the primary execution mechanism.

## Provenance

This decision supersedes and corrects an earlier draft dated 2026-04-11 that was written before the orchestrator had reconnaissance on the real system state. The earlier draft lived at `/Pi-CEO/Pi-SEO/architecture/ARCHITECTURE-MEMO.md` (now deleted) and assumed Pi-SEO needed to be built from scratch on the Mac Mini. That assumption was incorrect.

---

*End of decision record.*
