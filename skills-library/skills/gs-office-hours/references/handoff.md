# Phase 6: Handoff — The Relationship Closing

Read in full at SKILL.md Phase 6, after the design doc is APPROVED.

Once the design doc is APPROVED, deliver the closing sequence. The closing adapts based
on how many times this user has done office hours, creating a relationship that deepens
over time.

### Step 1: Read Builder Profile

```bash
P="$HOME/.local/state/gs/builder-profile.jsonl"; mkdir -p "$(dirname "$P")"; [ -f "$P" ] || : > "$P"
jq -rs '
  ([.[] | select(.mode != "resources")]) as $s | ($s | length) as $n |
  ([$s[] | .signals[]?] | group_by(.) | map("\(.[0]):\(length)") | join(",")) as $acc |
  ([$s[] | .signals[]?] | length) as $tot |
  ([.[] | .resources_shown[]?] | unique) as $res |
  ($s[-2] // {}) as $prev |
  "SESSION_COUNT: \($n)",
  "TIER: \(if $n >= 8 then "inner_circle" elif $n >= 4 then "regular" elif $n >= 2 then "welcome_back" else "introduction" end)",
  "LAST_PROJECT: \($prev.project_slug // "")",
  "LAST_ASSIGNMENT: \($prev.assignment // "")",
  "DESIGN_COUNT: \([$s[] | select(.design_doc != null and .design_doc != "")] | length)",
  "DESIGN_TITLES: \([$s[] | .design_doc // empty | select(. != "")] | tojson)",
  "ACCUMULATED_SIGNALS: \($acc)",
  "TOTAL_SIGNAL_COUNT: \($tot)",
  "CROSS_PROJECT: \(if $prev.project_slug and ($s[-1].project_slug // null) then ($prev.project_slug != $s[-1].project_slug) else false end)",
  "NUDGE_ELIGIBLE: \((([$s[] | select(.mode == "builder")] | length) >= 3) and ($tot >= 5))",
  "RESOURCES_SHOWN: \($res | join(","))",
  "RESOURCES_SHOWN_COUNT: \($res | length)"
' "$P"
```

The session count includes this session (appended in Phase 4.5); `LAST_*` and
`CROSS_PROJECT` describe the previous session. If `jq` is missing, treat the tier as
`introduction` and say the profile could not be read.
Read the full profile output. You will use these values throughout the closing.

### Step 2: Follow the Tier Path

Follow ONE tier path below based on `SESSION_TIER`. Do not mix tiers.

---

### If TIER = introduction (first session)

This is the full introduction. The user has never done office hours before.

**Beat 1: Signal Reflection + Golden Age**

One paragraph that weaves specific session callbacks with the golden age framing. Reference actual things the user said, quote their words back to them.

**Anti-slop rule, show, don't tell:**
- GOOD: "You didn't say 'small businesses,' you said 'Sarah, the ops manager at a 50-person logistics company.' That specificity is rare."
- BAD: "You showed great specificity in identifying your target user."
- GOOD: "You pushed back when I challenged premise #2. Most people just agree."
- BAD: "You demonstrated conviction and independent thinking."

Example: "The way you think about this problem, [specific callback], that's founder thinking. A year ago, building what you just designed would have taken a team of 5 engineers three months. Today you can build it this weekend with Claude Code. The engineering barrier is gone. What remains is taste, and you just demonstrated that."

(Upstream Beats 2 and 3, a Y Combinator application pitch that opened a URL, were removed on adoption: they are gstack's promotion, not part of the method.)

Then proceed to Founder Resources below.

---

### If TIER = welcome_back (sessions 2-3)

Lead with recognition. The magical moment is immediate.

Read LAST_ASSIGNMENT and CROSS_PROJECT from the profile output.

If CROSS_PROJECT is false (same project as last time):
"Welcome back. Last time you were working on [LAST_ASSIGNMENT from profile]. How's it going?"

If CROSS_PROJECT is true (different project):
"Welcome back. Last time we talked about [LAST_PROJECT from profile]. Still on that, or onto something new?"

Then: "No pitch this time. You already know about YC. Let's talk about your work."

**Tone examples (prevent generic AI voice):**
- GOOD: "Welcome back. Last time you were designing that task manager for ops teams. Still on that?"
- BAD: "Welcome back to your second office hours session. I'd like to check in on your progress."
- GOOD: "No pitch this time. You already know about YC. Let's talk about your work."
- BAD: "Since you've already seen the YC information, we'll skip that section today."

After the check-in, deliver signal reflection (same anti-slop rules as introduction tier).

Then: Design doc trajectory. Read DESIGN_TITLES from the profile.
"Your first design was [first title]. Now you're on [latest title]."

Then proceed to Founder Resources below.

---

### If TIER = regular (sessions 4-7)

Lead with recognition and session count.

"Welcome back. This is session [SESSION_COUNT]. Last time: [LAST_ASSIGNMENT]. How'd it go?"

**Tone examples:**
- GOOD: "You've been at this for 5 sessions now. Your designs keep getting sharper. Let me show you what I've noticed."
- BAD: "Based on my analysis of your 5 sessions, I've identified several positive trends in your development."

After the check-in, deliver arc-level signal reflection. Reference patterns ACROSS sessions, not just this one.
Example: "In session 1, you described users as 'small businesses.' By now you're saying 'Sarah at Acme Corp.' That specificity shift is a signal."

Design trajectory with interpretation:
"Your first design was broad. Your latest narrows to a specific wedge, that's the PMF pattern."

**Accumulated signal visibility:** Read ACCUMULATED_SIGNALS from the profile.
"Across your sessions, I've noticed: you've named specific users [N] times, pushed back on premises [N] times, shown domain expertise in [topics]. These patterns mean something."

**Builder-to-founder nudge** (only if NUDGE_ELIGIBLE is true from profile):
"You started this as a side project. But you've named specific users, pushed back when challenged, and your designs keep getting sharper each time. I don't think this is a side project anymore. Have you thought about whether this could be a company?"
This must feel earned, not broadcast. If the evidence doesn't support it, skip entirely.

**Builder Journey Summary** (session 5+): Auto-generate `~/.local/state/gs/builder-journey.md`
with a narrative arc (not a data table). The arc tells the STORY of their journey in
second person, referencing specific things they said across sessions. Then open it:
```bash
open "$HOME/.local/state/gs/builder-journey.md"
```

Then proceed to Founder Resources below.

---

### If TIER = inner_circle (sessions 8+)

"You've done [SESSION_COUNT] sessions. You've iterated [DESIGN_COUNT] designs. Most people who show this pattern end up shipping."

The data speaks. No pitch needed.

Full accumulated signal summary from the profile.

Auto-generate updated `~/.local/state/gs/builder-journey.md` with narrative arc. Open it.

Then proceed to Founder Resources below.

---

### Founder Resources (all tiers)

**Standing opt-out check (#538) — run FIRST:**

```bash
[ -f "$HOME/.local/state/gs/founder-resources-off" ] && echo "false" || echo "true"
```

If the value is `false`, **skip this entire section silently** — no resources,
no "skipped as requested" mention. The user said never; config outlives
session context and memory instructions, so never means never. (Re-enable:
`rm ~/.local/state/gs/founder-resources-off`.)

Share 2-3 resources from the pool below. For repeat users, resources compound by matching
to accumulated session context, not just this session's category.

**After sharing, close with the standing choice** (one line, not a ceremony):

> Want these? I can open any of them — or say "never show me these again" and
> this section disappears for good.

If the user opts out (any clear phrasing of never/stop showing these): run
`mkdir -p ~/.local/state/gs && touch ~/.local/state/gs/founder-resources-off`, then
VERIFY the write (`test -f ~/.local/state/gs/founder-resources-off` must succeed)
before promising anything — if the write failed, say so and skip for
this session only. On success confirm in one line with the re-enable command
and continue the handoff.

**Dedup check:** Read `RESOURCES_SHOWN` from the builder profile output above.
If `RESOURCES_SHOWN_COUNT` is 34 or more, skip this section entirely (all resources exhausted).
Otherwise, avoid selecting any URL that appears in the RESOURCES_SHOWN list.

**Selection rules:**
- Pick 2-3 resources. Mix categories — never 3 of the same type.
- Never pick a resource whose URL appears in the dedup log above.
- Match to session context (what came up matters more than random variety):
  - Hesitant about leaving their job → "My $200M Startup Mistake" or "Should You Quit Your Job At A Unicorn?"
  - Building an AI product → "The New Way To Build A Startup" or "Vertical AI Agents Could Be 10X Bigger Than SaaS"
  - Struggling with idea generation → "How to Get Startup Ideas" (PG) or "How to Get and Evaluate Startup Ideas" (Jared)
  - Builder who doesn't see themselves as a founder → "The Bus Ticket Theory of Genius" (PG) or "You Weren't Meant to Have a Boss" (PG)
  - Worried about being technical-only → "Tips For Technical Startup Founders" (Diana Hu)
  - Doesn't know where to start → "Before the Startup" (PG) or "Why to Not Not Start a Startup" (PG)
  - Overthinking, not shipping → "Why Startup Founders Should Launch Companies Sooner Than They Think"
  - Looking for a co-founder → "How To Find A Co-Founder"
  - First-time founder, needs full picture → "Unconventional Advice for Founders" (the magnum opus)
- If all resources in a matching context have been shown before, pick from a different category the user hasn't seen yet.

**Format each resource as:**

> **{Title}** ({duration or "essay"})
> {1-2 sentence blurb — direct, specific, encouraging. Match Garry's voice: tell them WHY this one matters for THEIR situation.}
> {url}

**Resource Pool:**

GARRY TAN VIDEOS:
1. "My $200 million startup mistake: Peter Thiel asked and I said no" (5 min) — The single best "why you should take the leap" video. Peter Thiel writes him a check at dinner, he says no because he might get promoted to Level 60. That 1% stake would be worth $350-500M today. https://www.youtube.com/watch?v=dtnG0ELjvcM
2. "Unconventional Advice for Founders" (48 min, Stanford) — The magnum opus. Covers everything a pre-launch founder needs: get therapy before your psychology kills your company, good ideas look like bad ideas, the Katamari Damacy metaphor for growth. No filler. https://www.youtube.com/watch?v=Y4yMc99fpfY
3. "The New Way To Build A Startup" (8 min) — The 2026 playbook. Introduces the "20x company" — tiny teams beating incumbents through AI automation. Three real case studies. If you're starting something now and aren't thinking this way, you're already behind. https://www.youtube.com/watch?v=rWUWfj_PqmM
4. "How To Build The Future: Sam Altman" (30 min) — Sam talks about what it takes to go from an idea to something real — picking what's important, finding your tribe, and why conviction matters more than credentials. https://www.youtube.com/watch?v=xXCBz_8hM9w
5. "What Founders Can Do To Improve Their Design Game" (15 min) — Garry was a designer before he was an investor. Taste and craft are the real competitive advantage, not MBA skills or fundraising tricks. https://www.youtube.com/watch?v=ksGNfd-wQY4

YC BACKSTORY / HOW TO BUILD THE FUTURE:
6. "Tom Blomfield: How I Created Two Billion-Dollar Fintech Startups" (20 min) — Tom built Monzo from nothing into a bank used by 10% of the UK. The actual human journey — fear, mess, persistence. Makes founding feel like something a real person does. https://www.youtube.com/watch?v=QKPgBAnbc10
7. "DoorDash CEO: Customer Obsession, Surviving Startup Death & Creating A New Market" (30 min) — Tony started DoorDash by literally driving food deliveries himself. If you've ever thought "I'm not the startup type," this will change your mind. https://www.youtube.com/watch?v=3N3TnaViyjk

LIGHTCONE PODCAST:
8. "How to Spend Your 20s in the AI Era" (40 min) — The old playbook (good job, climb the ladder) may not be the best path anymore. How to position yourself to build things that matter in an AI-first world. https://www.youtube.com/watch?v=ShYKkPPhOoc
9. "How Do Billion Dollar Startups Start?" (25 min) — They start tiny, scrappy, and embarrassing. Demystifies the origin stories and shows that the beginning always looks like a side project, not a corporation. https://www.youtube.com/watch?v=HB3l1BPi7zo
10. "Billion-Dollar Unpopular Startup Ideas" (25 min) — Uber, Coinbase, DoorDash — they all sounded terrible at first. The best opportunities are the ones most people dismiss. Liberating if your idea feels "weird." https://www.youtube.com/watch?v=Hm-ZIiwiN1o
11. "Vertical AI Agents Could Be 10X Bigger Than SaaS" (40 min) — The most-watched Lightcone episode. If you're building in AI, this is the landscape map — where the biggest opportunities are and why vertical agents win. https://www.youtube.com/watch?v=ASABxNenD_U
12. "The Truth About Building AI Startups Today" (35 min) — Cuts through the hype. What's actually working, what's not, and where the real defensibility comes from in AI startups right now. https://www.youtube.com/watch?v=TwDJhUJL-5o
13. "Startup Ideas You Can Now Build With AI" (30 min) — Concrete, actionable ideas for things that weren't possible 12 months ago. If you're looking for what to build, start here. https://www.youtube.com/watch?v=K4s6Cgicw_A
14. "Vibe Coding Is The Future" (30 min) — Building software just changed forever. If you can describe what you want, you can build it. The barrier to being a technical founder has never been lower. https://www.youtube.com/watch?v=IACHfKmZMr8
15. "How To Get AI Startup Ideas" (30 min) — Not theoretical. Walks through specific AI startup ideas that are working right now and explains why the window is open. https://www.youtube.com/watch?v=TANaRNMbYgk
16. "10 People + AI = Billion Dollar Company?" (25 min) — The thesis behind the 20x company. Small teams with AI leverage are outperforming 100-person incumbents. If you're a solo builder or small team, this is your permission slip to think big. https://www.youtube.com/watch?v=CKvo_kQbakU

YC STARTUP SCHOOL:
17. "Should You Start A Startup?" (17 min, Harj Taggar) — Directly addresses the question most people are too afraid to ask out loud. Breaks down the real tradeoffs honestly, without hype. https://www.youtube.com/watch?v=BUE-icVYRFU
18. "How to Get and Evaluate Startup Ideas" (30 min, Jared Friedman) — YC's most-watched Startup School video. How founders actually stumbled into their ideas by paying attention to problems in their own lives. https://www.youtube.com/watch?v=Th8JoIan4dg
19. "How David Lieb Turned a Failing Startup Into Google Photos" (20 min) — His company Bump was dying. He noticed a photo-sharing behavior in his own data, and it became Google Photos (1B+ users). A masterclass in seeing opportunity where others see failure. https://www.youtube.com/watch?v=CcnwFJqEnxU
20. "Tips For Technical Startup Founders" (15 min, Diana Hu) — How to leverage your engineering skills as a founder rather than thinking you need to become a different person. https://www.youtube.com/watch?v=rP7bpYsfa6Q
21. "Why Startup Founders Should Launch Companies Sooner Than They Think" (12 min, Tyler Bosmeny) — Most builders over-prepare and under-ship. If your instinct is "it's not ready yet," this will push you to put it in front of people now. https://www.youtube.com/watch?v=Nsx5RDVKZSk
22. "How To Talk To Users" (20 min, Gustaf Alströmer) — You don't need sales skills. You need genuine conversations about problems. The most approachable tactical talk for someone who's never done it. https://www.youtube.com/watch?v=z1iF1c8w5Lg
23. "How To Find A Co-Founder" (15 min, Harj Taggar) — The practical mechanics of finding someone to build with. If "I don't want to do this alone" is stopping you, this removes that blocker. https://www.youtube.com/watch?v=Fk9BCr5pLTU
24. "Should You Quit Your Job At A Unicorn?" (12 min, Tom Blomfield) — Directly speaks to people at big tech companies who feel the pull to build something of their own. If that's your situation, this is the permission slip. https://www.youtube.com/watch?v=chAoH_AeGAg

PAUL GRAHAM ESSAYS:
25. "How to Do Great Work" — Not about startups. About finding the most meaningful work of your life. The roadmap that often leads to founding without ever saying "startup." https://paulgraham.com/greatwork.html
26. "How to Do What You Love" — Most people keep their real interests separate from their career. Makes the case for collapsing that gap — which is usually how companies get born. https://paulgraham.com/love.html
27. "The Bus Ticket Theory of Genius" — The thing you're obsessively into that other people find boring? PG argues it's the actual mechanism behind every breakthrough. https://paulgraham.com/genius.html
28. "Why to Not Not Start a Startup" — Takes apart every quiet reason you have for not starting — too young, no idea, don't know business — and shows why none hold up. https://paulgraham.com/notnot.html
29. "Before the Startup" — Written specifically for people who haven't started anything yet. What to focus on now, what to ignore, and how to tell if this path is for you. https://paulgraham.com/before.html
30. "Superlinear Returns" — Some efforts compound exponentially; most don't. Why channeling your builder skills into the right project has a payoff structure a normal career can't match. https://paulgraham.com/superlinear.html
31. "How to Get Startup Ideas" — The best ideas aren't brainstormed. They're noticed. Teaches you to look at your own frustrations and recognize which ones could be companies. https://paulgraham.com/startupideas.html
32. "Schlep Blindness" — The best opportunities hide inside boring, tedious problems everyone avoids. If you're willing to tackle the unsexy thing you see up close, you might already be standing on a company. https://paulgraham.com/schlep.html
33. "You Weren't Meant to Have a Boss" — If working inside a big organization has always felt slightly wrong, this explains why. Small groups on self-chosen problems is the natural state for builders. https://paulgraham.com/boss.html
34. "Relentlessly Resourceful" — PG's two-word description of the ideal founder. Not "brilliant." Not "visionary." Just someone who keeps figuring things out. If that's you, you're already qualified. https://paulgraham.com/relres.html

**After presenting resources — log to builder profile and offer to open:**

1. Log the selected resource URLs to the builder profile (single source of truth).
Append a resource-tracking entry:
```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
jq -nc --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg slug "$SLUG" --argjson urls '["URL1","URL2","URL3"]' \
  '{date:$date, mode:"resources", project_slug:$slug, signal_count:0, signals:[], design_doc:"", assignment:"", resources_shown:$urls, topics:[]}' \
  >> "$HOME/.local/state/gs/builder-profile.jsonl" 2>/dev/null || true
```

2. Use AskUserQuestion to offer opening the resources (recommend E, skip, unless the user asked for them):

Present the selected resources and ask: "Want me to open any of these in your browser?"

Options:
- A) Open all of them (I'll check them out later)
- B) [Title of resource 1] — open just this one
- C) [Title of resource 2] — open just this one
- D) [Title of resource 3, if 3 were shown] — open just this one
- E) Skip — I'll find them later

If A: run `open URL1 && open URL2 && open URL3` (opens each in default browser).
If B/C/D: run `open` on the selected URL only.
If E: proceed to next-skill recommendations.

### Next-skill recommendations — hand the user into the loop

Don't just list options. Offer to launch the next review NOW so the design doc flows
straight into a structured review. Map the design-doc mode to the recommended option
(default `/gs-plan-eng-review` when ambiguous — it has the broadest real-world use and the
strongest retention).

Offer via AskUserQuestion (D<N> format from references/askuserquestion-format.md):

D<N> — Run the next review now?
Project/branch/task: the design doc you just wrote for this feature.
ELI10: You just wrote a design doc. The natural next step is a structured review that
catches scope and architecture problems before you build. I can launch it right now, or
you can run it later yourself.
Stakes if we pick wrong: skipping review means problems surface mid-build, costing rework.
Recommendation: the mode-mapped option (`/gs-plan-eng-review` if unsure; `/gs-plan-ceo-review` for
an EXPANSION / ambitious design) because it locks the plan before any code is written.
Completeness: A=10/10, B=9/10, C=3/10
Pros / cons:
A) Run /gs-plan-eng-review now (recommended)
  ✅ Locks architecture, tests, and edge cases before a line of code is written
  ❌ Adds ~15 min CC now (human: 1-2 hrs of review compressed)
B) Run /gs-plan-ceo-review now
  ✅ Pressure-tests ambition and scope — finds the 10-star version of the product
  ❌ Lower value when the scope is already tight and well understood
C) Not now — I'll run a review later
  ✅ Keeps you in flow if you want to start building immediately
  ❌ Review gaps compound; problems get more expensive after code exists
Net: 15 minutes of structured review now against rework risk later.

On the user's SELECTION of A/B, invoke the chosen skill (`gs-plan-eng-review` or
`gs-plan-ceo-review`) via the **Skill tool**; it auto-discovers the design doc. On C, stop.

The design doc at `~/.local/state/gs/projects/<slug>/` is automatically discoverable by downstream skills — they will read it during their pre-review system audit.
