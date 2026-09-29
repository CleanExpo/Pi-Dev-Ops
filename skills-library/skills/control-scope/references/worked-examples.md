# Control Scope — worked examples in full

The incidents behind the rules in `SKILL.md` — §1–§5 below. Each is an occasion where a *sound*
instrument was aimed at the wrong surface and produced output indistinguishable from a clean
result.

`control-scope` was split out of `control-design` on 2026-08-03, which had grown to 495 lines.
Soundness and scope read as one topic while writing and as two topics while debugging.

## 1. Mode 7 — the positive control that validated the instrument, not the aim

*2026-08-02, Pi-Dev-Ops.*

Auditing which API routes enforce auth, I searched for `middleware.ts`, found none, and ran a
positive control: the same glob shape returned 26 `route.ts` files, so the search plainly
worked. I concluded there was no central auth layer and began assembling ~13 "unauthenticated"
handlers with exploit chains — unauthenticated settings writes that could rewrite the GitHub
webhook secret, arbitrary repo commits, a session-table wipe. Serious, specific, and wrong.

**Next.js 16 renamed `middleware.ts` to `proxy.ts`.** The file was there the whole time, under a
name I never searched for. `proxy.ts` gates seven path prefixes; all thirteen findings collapsed.

My positive control confirmed the glob functioned. It could not confirm the filename was
current, because it never tested that — and nothing in an empty result says which of the two
failed.

What caught it was **not more source reading**. More reading would have re-derived the same
wrong answer from the same wrong premise, with rising confidence. It was a live probe: `curl`
against production returned 401 on two routes my analysis said were wide open. Reality
disagreeing with the model is the only signal that escapes a self-consistent misreading.

```bash
# WRONG — proves the glob runs, not that the name is right
ls **/middleware.ts || echo "no central auth"     # the NAME is an untested assumption

# RIGHT — search for behaviour, then ask reality
grep -rlE "PROTECTED_API|PUBLIC_API|verifySession" --include="*.ts" . | head
curl -s -o /dev/null -w "%{http_code}" https://prod.example/api/thing   # 401 ≠ your model
```

## 2. Claim-shape — "confirmed by discovery" after a narrowed search

*2026-08-02.*

A broad sweep for anything invoking `autogit` was launched, ran past its timeout, and was
backgrounded. It was replaced with a targeted sweep over specific config files, which returned
clean. That was reported as **"confirmed by discovery: nothing else invokes autogit"**.

The broad sweep later completed and found `~/.codex/hooks.json.bak-20260717-autogit` — a backup
holding all four removed hook entries, one copy command from re-arming, in the same directory as
the file that *was* checked.

The targeted sweep checked `hooks.json`. It did not check `hooks.json.bak-*`. Both statements
below are true, and only one was written:

- ✅ *"confirmed within targeted scope: hooks.json, project `.codex/`, git hooks, scheduled tasks"*
- ❌ *"confirmed by discovery"*

The gap between those sentences is where the finding lived. The narrowing was reasonable — the
broad search genuinely was too slow. **The defect was upgrading the claim to match the intent
rather than the method.**

This one matters most because mode 7 had been written down **the same day, hours earlier, by the
same process that then repeated it.** Prose did not prevent recurrence, which is why claim-shape
is expressed as a rule about sentence shape rather than as advice.

## 3. Canary placement — the two-arm test that exposed a blind scanner

*2026-08-03.*

The claim on the table was that 28 `.harness/` files were *"scanned clean with the canary"*. Same
fake `AKIA`-shaped value, planted twice, directory the only variable:

| arm | path | result |
|---|---|---|
| A | `docs/zzcontrol-arm-b.txt` | **DETECTED CRITICAL** |
| B | `.harness/zzcontrol-arm-a.txt` | **not scanned, missed** |

`scripts/secrets_check.py` lists `".harness/"` in `_SKIP_PATH_PREFIXES`. It is structurally
incapable of returning a finding there. Any canary that produced that PASS was planted in arm A —
a surface the scanner was already known to reach — so the PASS could never have covered the files
the claim named.

Rescanned with an instrument that does reach them (28/28, then 608/608 positive control), the
files were in fact clean **and** a live-shaped `TELEGRAM_BOT_TOKEN` sat in
`.harness/n8n-workflows/RA-649-IMPORT-INSTRUCTIONS.md:15`, which the blind instrument had never
been able to see.

### Three instances in two days

| date | instrument | what it could not see | conclusion |
|---|---|---|---|
| 2026-08-01 | `secrets_check.py --exclude-standard` | every gitignored file — `.env.local`, `*.pem`, credential dumps | held |
| 2026-08-02 | targeted `autogit` sweep replacing a timed-out broad one | `hooks.json.bak-*` beside the file that *was* checked | **failed** |
| 2026-08-03 | `secrets_check.py` with `.harness/` in `_SKIP_PATH_PREFIXES` | 608 tracked `.harness` files | held, live token inside the blind spot |

Two of the three conclusions survived scrutiny. One did not. **Nothing in the output
distinguished them at the time** — all three read as clean. That is the whole danger: the
conclusion being right is not evidence the instrument was, and a right conclusion from a blind
instrument is luck that reports identically to rigour.

Same epistemics as an alert channel. A channel that has been blinded and a channel with nothing
to say both produce silence; you cannot tell them apart by listening harder, only by sending a
known message through and watching it arrive.

## 4. The drift-check that exists on a branch and protects nothing

*2026-08-03.* `control-design/SKILL.md` stated that `skills-drift-check` "fails the build if the
two diverge", enforcing repo-canonical over the `~/.claude/skills/` deploy artifact. The repo copy
stood at 424 lines against the machine copy's 495 — **71 lines of undetected drift**.

**First conclusion, and it was wrong:** a `grep` found `skills-drift-check` only in `.harness/`
notes and in that SKILL.md sentence, so I reported it as named but never built.

**Mode 7 again, in the file documenting mode 7.** `.github/workflows/skills-drift-check.yml`
exists, under exactly the name searched for — on the unmerged branch
`feat/command-centre-migration`. The grep ran over the checked-out working tree; the claim covered
every tree. Nothing in the empty result distinguished "not built" from "not on this branch".

**The corrected finding is worse than the wrong one.** A control that exists only on an unmerged
branch has protected nothing, while reading — to anyone who sees the filename in a PR or a
workflow list — as though it does. "Named but never built" at least invites someone to build it;
"built, merged nowhere" looks finished.

**The rule:** before concluding a control does not exist, search every ref —
`git grep <name> --all`, or `git log --all --diff-filter=A -- <path>` — not the tree you happen
to have checked out. And before trusting one that does exist, confirm it runs on the branch you
care about. Per `control-readout`: a control that never executed has unknown state, not good
state.

## 5. Naming the risk — the brief that described the gap I then shipped

*2026-08-02.*

The hardening review brief I authored told the reviewer to check *"nested objects, arrays of
objects"* — and I then shipped a guard that checked only top-level keys. The reviewer found
precisely the thing I had written down. `proposals` is an array of objects; the entire payload
sat one level below where I was looking.

The shape is almost comic, and that is what makes it worth keeping: the gap was not unknown,
unconsidered or hard to see. It was *written down, by me, in the document commissioning the
check* — and written down is where it stayed. Awareness travelled into prose instead of into a
control, and prose does not fail a build.

**The rule:** a gap you wrote down is still open. Writing it down changes who is surprised, not
whether it is exploitable. Either build the check, or record it as a deferral with a named
blocker and an unblock condition, so the next reader can tell a decision from an intention.
