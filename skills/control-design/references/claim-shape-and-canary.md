# Claim-shape and canary-placement rules

Moved verbatim from SKILL.md.

## CLAIM-SHAPE RULE — a narrowed instrument produces a narrowed claim, mechanically

Failure mode 7 says a positive control validates the instrument and not the aim. That was
written down on 2026-08-02 and **recurred the same day, hours later, by the same process that
wrote it.** Prose did not prevent it. What follows is therefore not advice; it is a rule about
the SHAPE of the sentence you are permitted to write.

### The rule

**Whenever an instrument is narrowed — for cost, speed, timeout, context, or convenience — the
narrowing enters the claim as a qualifier, or the claim is invalid.**

| you ran | the ONLY claim you may write |
|---|---|
| a search over selected paths | "confirmed **within targeted scope**: `<paths>`" |
| a broad search that completed | "confirmed **by discovery**" |
| a search that timed out and was replaced | "confirmed **within reduced scope**; the broad search did not complete" |
| a check that skipped anything | "confirmed **excluding** `<exclusions>`" |

`confirmed by discovery` is reserved for a search that was **not** narrowed and **did** complete.
Writing it after running a narrowed search is the defect — not the narrowing, which is often
correct and necessary. **Narrowing is legitimate. Reporting it as breadth is not.**

### Mechanical trigger

Any of these means the claim MUST carry a scope qualifier:

- you replaced a running search with a faster one
- you added `-maxdepth`, `--include`, a path list, `head`, or a `limit`
- a command timed out, was backgrounded, or was killed
- you scanned "the file" rather than "files matching the pattern"
- you sampled N of M

### Worked example — the recurrence this rule exists to stop

*2026-08-02.* A broad sweep for anything invoking `autogit` was launched, ran past its timeout,
and was backgrounded. It was replaced with a targeted sweep over specific config files, which
returned clean. That was reported as **"confirmed by discovery: nothing else invokes autogit"**.

The broad sweep later completed and found `~/.codex/hooks.json.bak-20260717-autogit` — a backup
holding all four removed hook entries, one copy command from re-arming, in the same directory
as the file that *was* checked.

The targeted sweep checked `hooks.json`. It did not check `hooks.json.bak-*`. Both statements
below are true, and only one was written:

- ✅ *"confirmed within targeted scope: hooks.json, project `.codex/`, git hooks, scheduled tasks"*
- ❌ *"confirmed by discovery"*

The gap between those two sentences is where the finding lived. The narrowing was reasonable —
the broad search genuinely was too slow. **The defect was upgrading the claim to match the
intent rather than the method.**

### The check to run on your own sentence

Before writing any confirming claim, ask: *what did my instrument physically not look at?* If
the answer is anything at all, it goes in the sentence. If you cannot enumerate what was
excluded, you do not know your own scope, and no confirming claim is available to you yet.

## CANARY-PLACEMENT RULE — plant the control on the surface the claim covers

The claim-shape rule governs the sentence you write after the run. This one governs where you
put the canary before it. They are the same defect caught at two different moments, and the
catalogue needs both because the claim-shape rule only fires if you already suspect your scope.

### The rule

**A positive control must be planted on the surface the claim covers — not on a surface the
instrument is already known to reach.**

A canary planted where the instrument demonstrably works measures nothing you did not already
have. It re-proves reachability at a location that was never in doubt, and then that PASS gets
carried across a boundary it never crossed. The only informative placement is the surface you
are about to make a claim about.

### The two-arm form

Plant the **same value twice**. Vary **only** the property under suspicion — directory,
extension, tracked-vs-ignored, environment, tenant, branch. One arm must land where the
instrument is known to work; that arm is the sanity check on the canary itself. The other lands
on the claimed surface. **A canary detected in arm A and missed in arm B is the finding.**

One arm alone cannot distinguish "the surface is clean" from "the instrument never looked".

### Worked example — 2026-08-03

The claim on the table was that 28 `.harness/` files were *"scanned clean with the canary"*.
Same fake `AKIA`-shaped value, planted twice, directory the only variable:

| arm | path | result |
|---|---|---|
| A | `docs/zzcontrol-arm-b.txt` | **DETECTED CRITICAL** |
| B | `.harness/zzcontrol-arm-a.txt` | **not scanned, missed** |

`scripts/secrets_check.py` lists `".harness/"` in `_SKIP_PATH_PREFIXES`. It is structurally
incapable of returning a finding there. Any canary that produced that PASS was planted in arm A
— a surface the scanner was already known to reach — so the PASS could never have covered the
files the claim named. Rescanned with an instrument that does reach them (28/28, then 608/608
positive control), the files were in fact clean **and** a live-shaped `TELEGRAM_BOT_TOKEN` sat in
`.harness/n8n-workflows/RA-649-IMPORT-INSTRUCTIONS.md:15`, which the blind instrument had never
been able to see.

### Three instances in two days

| date | instrument | what it could not see | conclusion |
|---|---|---|---|
| 2026-08-01 | `secrets_check.py` with `--exclude-standard` | every gitignored file — `.env.local`, `*.pem`, credential dumps | held |
| 2026-08-02 | targeted `autogit` sweep replacing a timed-out broad one | `hooks.json.bak-*` beside the file that *was* checked | **failed** — the `.bak` held all four removed entries |
| 2026-08-03 | `secrets_check.py` with `.harness/` in `_SKIP_PATH_PREFIXES` | 608 tracked `.harness` files on `feat/command-centre-migration` | held, and a live token was sitting inside the blind spot |

Two of the three conclusions survived scrutiny. One did not. **Nothing in the output
distinguished them at the time** — all three read as clean. That is the whole danger: the
conclusion being right is not evidence the instrument was, and a right conclusion from a blind
instrument is luck that reports identically to rigour.

This is the same epistemics as an alert channel. A channel that has been blinded and a channel
with nothing to say both produce silence; you cannot tell them apart by listening harder, only
by sending a known message through and watching it arrive. A canary is that known message, and
it has to travel the path you are making a claim about.

### The check to run before planting

- What property do I suspect the instrument of being blind to?
- Does my canary vary that property, and nothing else?
- Which arm lands on the surface my claim will name?
- If both arms detect, my canary proves reachability and **not** cleanliness — the real run
  still has to happen.
- A control that cannot fail cannot inform. If no placement could have produced a miss, I have
  not designed a control; I have designed a formality.
