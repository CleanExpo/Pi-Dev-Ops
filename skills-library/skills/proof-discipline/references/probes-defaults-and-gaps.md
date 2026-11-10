# Proof Discipline: counting probes, default branches and unclassified gaps

Moved from SKILL.md. Read when a probe's number, a fallback path or a coverage hole is in play.

### A COUNTING PROBE NEEDS A KNOWN-N FIXTURE, NOT A NON-EMPTY ASSERTION

`mutate-assert.py` cannot catch this class, and that is the point: it proves a probe **found
something**. It cannot prove the probe is **counting the right thing**. The target matches, the
output is non-empty, the control fires — and the number is still wrong.

Every instance returned a plausible, specific number that nobody had a known-correct value to
compare against:

| probe | reported | actual | mechanism |
|---|---|---|---|
| `grep -c $'\r' f` | 120 / 53 / 83 | 0 | `$'\r'` did not expand → `grep -c ''` matches every line, so the counts were file *lengths* |
| `find -maxdepth 4` | 146 | 1,021 | depth cap silently truncated the walk |
| `MANIFEST*` glob | 83 | 19 | matched a JSON schema that was not the skills manifest |

**The rule: before believing a count, plant a fixture whose N you chose, and assert the probe
returns exactly that N.** Three CRLF lines → expect 3. Nine files at depth 6 → expect 9. If the
probe cannot see the planted fixture, every number it has ever produced is uninterpreted.

A count is a measurement. `> 0` is not a calibration.

## A DEFAULT BRANCH IS THE UNTESTED BRANCH

When a parameter has a fallback, tests supply the parameter. The default path is the one
nobody exercises — and it is where the wrong destination, the loop, and the unvalidated input
all sit.

**The instance.** A login page reads `?redirect=`, falling back to a hardcoded path. Three
defects lived on the no-param branch at once: the fallback pointed outside the zone (a
post-login 404 on success), the login path was inside its own protected prefix (redirect
loop), and the param was passed to `router.push` unvalidated (an open redirect, which on a
public login page is a phishing primitive). A redirect round-trip test always supplies the
param, so it passes over all three.

Three defects behind one blind spot is not coincidence — it is a test-design defect. **Probe
the default branch explicitly**, by omitting the parameter, not by supplying a typical one.

## AN UNCLASSIFIED THING IS NOT MERELY UNGUARDED — SUSPECT IT IS ALSO BROKEN

The most useful correlation of 2026-08-02, and it was visible only once two separate
investigations were laid side by side.

- The routes with **no auth classification** — outside both proxy prefix lists, absent from
  `api-auth-classification.json` — were `kill-switch`, `zte`, `swarm-status`,
  `curator-proposals`.
- The routes sending the **wrong credential type upstream**, and therefore never working at
  all, were `kill-switch`, `zte`, `swarm-status`, `curator-proposals`.

The same four. Not a coincidence, and not two bugs: **routes nobody classified are routes
nobody thought about, and unexamined code is broken at whatever rate code is born broken.** The
missing guard and the missing wiring have one cause, which is that no one ever looked.

**So a classification file is not a security artefact. It is a map of what has been thought
about.** Read it that way and it says more than it was built to say:

- An entry means someone reasoned about this surface. The reasoning may be wrong, but it exists.
- **A gap means nobody has.** Treat the gap as evidence of *general* neglect, not merely of a
  missing guard — check whether the thing works at all, not just whether it is protected.

The practical rule: when a coverage map shows a hole, do not only close the hole. **Go and test
whether the uncovered thing functions.** In this instance every unclassified route was also
non-functional, and the non-functionality had been invisible for 92 days because the routes
returned quiet 200s. Finding the gap was cheap; only looking through it found the real defect.
