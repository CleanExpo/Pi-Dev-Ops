# Failure modes 6 and 7 in full

Moved verbatim from SKILL.md.

### 6 in full — verify a control's precondition before trusting the control

A negative control only proves something if the thing you removed **was present to remove**.
Delete a token that was never there and you have planted nothing: the suite passes, and the
pass says nothing at all about whether the check can fail.

This is the same class as a query suite going green because 19 DB-gated files silently
skipped, or a `grep` whose alternation never matched — **a clean result from a check that
never ran looks identical to a clean result from a clean system.**

It bites hardest on *exemptions*. When you write a rule and then exempt yourself from it, the
control proving the exemption is still narrow is the only thing standing between "declared" and
"disabled" — so a vacuous control there is worse than none, because it manufactures confidence.

```bash
# WRONG — proves nothing if the token was absent
sed -i 's/disabled/_removed/' target.ts && run_suite     # suite passes… of what?

# RIGHT — the precondition is asserted first, and a no-op is fatal
grep -q 'disabled' target.ts || { echo "anchor absent — control would be vacuous"; exit 1; }
sed -i 's/disabled/_removed/' target.ts
grep -c '_removed' target.ts        # must be >= 1
run_suite                            # NOW a pass/fail means something
```

**If the anchor is absent, do not substitute a different control silently — say the control
could not be run, and find one whose precondition holds.**

**This file was itself failure mode 4.** It lived only at `~/.claude/skills/`, which is
gitignored and does not travel, so the lesson about verification proving nothing existed on
one machine and nowhere else. Deployed-versus-template drift, biting the document that
catalogues it. Ruling 2026-08-01: **the repo is canonical, the machine copy is a deploy
artifact, one-way repo → machine, never the reverse.** Editing `~/.claude/skills/` in place is
editing files on a production server. `skills-drift-check` fails the build if the two diverge.

*Earned 2026-08-01: a per-file per-rule exemption was reported as "controlled" after an attempt
to remove a `disabled` token from a file that contained none. Nothing was planted; the 22/22
pass was meaningless. The real control — planting an **undeclared** construct in the same file —
failed 2 tests, which is what the exemption's narrowness actually rests on.*

### 7 in full — a positive control validates the instrument, not the aim

A positive control proves your search *mechanism* works. It says nothing about whether you
pointed it at the right target. Both failures emit the identical output — an empty result from
a correctly-functioning search — and only one of them means "absent".

Mode 6 is *the control could not have failed*. Mode 7 is *the control worked perfectly and was
aimed at the wrong thing*. Running 6 does not protect you from 7; in the incident below, the
positive control **passed**, which is precisely what made the wrong conclusion feel earned.

*Earned 2026-08-02, Pi-Dev-Ops.* Auditing which API routes enforce auth, I searched for
`middleware.ts`, found none, and ran a positive control: the same glob shape returned 26
`route.ts` files, so the search plainly worked. I concluded there was no central auth layer and
began assembling ~13 "unauthenticated" handlers with exploit chains — unauthenticated settings
writes that could rewrite the GitHub webhook secret, arbitrary repo commits, a session-table
wipe. Serious, specific, and wrong.

**Next.js 16 renamed `middleware.ts` to `proxy.ts`.** The file was there the whole time, under a
name I never searched for. `proxy.ts` gates seven path prefixes; all thirteen of my findings
collapsed. My positive control had confirmed the glob functioned. It could not confirm the
filename was current, because it never tested that — and nothing in an empty result says which
of the two failed.

What caught it was **not more source reading**. More reading would have re-derived the same
wrong answer from the same wrong premise, with rising confidence. It was a live probe: `curl`
against production returned 401 on two routes my analysis said were wide open. Reality
disagreed with the model, which is the only signal that can escape a self-consistent misreading.

```bash
# WRONG — the control proves the glob runs, not that the name is right
ls **/middleware.ts || echo "no central auth"     # the NAME is an untested assumption

# RIGHT — search for the behaviour, then ask reality
grep -rlE "PROTECTED_API|PUBLIC_API|verifySession" --include="*.ts" . | head
curl -s -o /dev/null -w "%{http_code}" https://prod.example/api/thing   # 401 ≠ your model
```

Rules that follow:
- Framework-defined filenames are **version-dependent**. Check the convention for the version in
  `package.json` before treating absence of a file as absence of a mechanism.
- Prefer searching for **behaviour** (a distinctive identifier, constant, or call) over a
  **filename**. Behaviour survives renames; filenames do not.
- When a source-only reading concludes something is exposed, **probe it before reporting**. Use
  a read-only endpoint, and never let the probe be the exploit.
- Report the aim, not just the result. "No file named X" is not "no such mechanism", and the
  gap between those two sentences is where this failure lives.
