---
name: credential-custody
description: "Use when a secret, token, password or key is about to be written into a test, handled during a verification, or read at startup. Answers one question: does anything have to TOUCH the secret that should not? Catches fixtures that write literal secret-shaped values, verification steps that ask a human to retrieve and paste the protected value, and missing-config branches that invent a credential instead of refusing to start."
---

# Credential Custody — does anything have to TOUCH the secret?

**One question only.** *Will this control fire when the defect is present?* is
[`control-design`](../control-design/SKILL.md). *What did the instrument look at, and what may I
claim?* is [`control-scope`](../control-scope/SKILL.md). Reading a verdict you did not write:
[`control-readout`](../control-readout/SKILL.md).

Split out of `control-design` on 2026-08-04, at 232 lines. These three rules had travelled with
it because they arrived in the same sessions — not because they answer its question. None of
them is about whether a check can fail. They are about **who ends up holding the value**, and
they fail the same way each time: the convenient path requires someone, or something, to handle
the protected thing, and the handling is where it leaks.

**The one line to carry:** *when the convenient path requires handling the protected thing, the
convenience is being purchased with the protection.*

## Test fixtures generate secret-shaped values; they never write them as literals

A secrets scanner **cannot tell a fixture from a credential by reading it.** That is correct
behaviour, and the reason the estate's JWT pattern is deliberately broad enough to match public
anon keys.

**Rule:** a test needing a password, token, secret or key generates it at runtime
(`randomBytes(24).toString("hex")`). Never a literal, however obviously fake.

**Why the obvious alternative is the trap.** When a fixture trips the scanner, adding a skip
prefix or widening the placeholder regex looks like the reasonable fix. It is not: it narrows
the scanner permanently to accommodate one file, and **that is the path by which a real secret
eventually walks through.** The fix that stops today's alarm is the one that disables tomorrow's.

Two instances, both caught by the scanner rather than by review: a hardcoded probe password in
`scripts/route-exercise.mjs`, and `const KS_SECRET = "kill-switch-shared-secret"` failing CI on
PR #603. Its sibling one line above escaped only by accident — `"kill-switch-test-secret"`
contains `test-secret`, which the placeholder regex excludes. Both fixed by generating the
value, not by teaching the scanner to look away.

## A verification that requires handling the thing it protects is a design failure

**No matter how careful the handling instructions are.** If a procedure says *retrieve the
secret, paste it here, and be careful* — the design is already wrong. Careful handling is not a
control; it is a request that every future operator be careful every time, and it fails the day
someone is tired or pastes into the wrong window.

**The test:** can the verification run without any human ever seeing the value? If not,
redesign the verification, do not improve the instructions.

*2026-08-02.* `KILL_SWITCH_SECRET` was generated straight into Vercel through a pipe and
deliberately never read back — held by nobody. The verification then designed to prove it
worked asked the founder to **retrieve it from the dashboard and paste it into a `curl`**. It
landed in the agent transcript, exactly the place the design existed to avoid; the secret had to
be rotated. The *remediation* then repeated the shape — "add the new value to the GitHub
Environment" required retrieving and pasting again. **A design failure of this kind recurs in
its own fix**, because the instinct that produced it is still operating.

The correct design costs nothing: **generate once and dual-write** — one freshly generated value
piped into both stores in a single command.

**The honest part.** The manual probe was recommended before the CI proof for a real reason: it
is debuggable, one command, immediate answer. That benefit is real and is why it felt
reasonable. It was outweighed. **When the convenient path requires handling the protected thing,
the convenience is being purchased with the protection.** Build the plumbing.

## A service that invents its own credential has no failure mode — it has a silent reconfiguration mode

```python
if not _raw_password:  _raw_password = secrets.token_urlsafe(24)   # app/server/config.py
else: SESSION_SECRET = secrets.token_hex(32); _SECRET_FILE.write_text(SESSION_SECRET)
```

When `TAO_PASSWORD` is unset the server generates a random password, logs it once, and persists
a bcrypt hash. Usually written as convenience — "so it still boots" — and it is the most
dangerous shape a missing-config branch can take.

**A missing credential is a loud, diagnosable fault. An invented one is not a fault at all.**
The service starts, reports healthy, and rejects every legitimate client. Nothing logs an error,
because from the service's point of view nothing went wrong. The symptom appears at the
*caller*, as an auth failure, routing the investigation to the caller's credential — the one
thing that is not broken.

Worse with ephemeral storage: persistence is to a container filesystem, so **a redeploy can
rotate the credential to a value nobody holds**, at a moment unrelated to any change anyone made.

**The correct behaviour is refuse-to-start.** An unavailable service is diagnosable in seconds;
an inaccessible one is not. Auto-generation is defensible only for a genuinely single-user local
dev default, and even then must be impossible in a deployed environment.

*Recorded 2026-08-02 as a proposal, not a change.* Whether Pi CEO upstream actually had
`TAO_PASSWORD` unset was never established. The finding stands regardless: the branch exists,
and while it exists this fault is always available.
