# Reviewer-isolation remediation queue

**Status: RECORDED, NOT ACTED ON.** Filed 2026-08-03 by founder direction during PART 2 of the
config-move work order.

These are **hypotheses to measure, not facts**. Each one gets its own measurement before any
fix. Nothing here is a defect report yet — several may turn out to be already satisfied, and
one of them (item six) is a correction to a control that already exists.

Context: a reviewer process running an external model was measured reading the operator's SSH
private key, Railway token and cloud credentials, with open network egress and write access
outside the working tree. A proposal isolates it in a Docker container. A paper review of that
proposal produced the items below. **The container is not in use.** Nothing here blocks the
config move.

---

## 1. Mount manifest — ancestors, not only descendants

The manifest must reject any read-write bind that is an **ancestor** of the repository, not
only one inside it. Read-only is a property of a mount point, not of a host inode: `-v /host:rw`
alongside `-v /host/repo:ro` leaves the tree writable through the first path while probes of
the second correctly report EROFS.

**Measure:** enumerate every bind in the launch configuration, resolve each to a host path, and
assert that none is a prefix of the repository path.

## 2. Disposable-copy acceptance test — add a positive control

The stated acceptance test ("if any writable path reaches the host tree, it has failed") has no
arm proving a write was genuinely attempted and genuinely failed. A malformed probe returns
"cannot write" for every arm, and total failure is indistinguishable from total success.

The mount-boundary proof already has this and should be the model: its EROFS arm on a tracked
source file is what makes its ENOENT arm meaningful.

**Measure:** the test must fail when pointed at a path that is actually writable.

## 3. Network plane is untested

The two-arm probe tested host **filesystem** routes. Container-to-host network reachability was
not measured. From the default bridge, `host.docker.internal` / the gateway address reaches
services on the host loopback — **including the Pi-CEO server on port 7777**, which
`scripts/handoff-loop.sh` itself probes at `http://127.0.0.1:7777/health`.

**Measure:** from inside the container, attempt to reach `7777` on the gateway address and on
`host.docker.internal`, and record what answers.

## 4. What environment does the launcher actually pass?

Determine exactly which variables enter the container, and specifically whether any bare-name
passthrough (`environment: - RAILWAY_TOKEN`, no value) or `--env-file` carries the operator's
shell environment. The model API key is in there by necessity; the question is what else.

**Measure:** dump the container's environment and diff it against the minimum the reviewer needs.

## 5. Write the loop split down

Anything requiring the Docker daemon runs **host-side, before launch**. The container runs only
what works without the socket. Write this down explicitly so a later convenience commit has
something to violate.

This exists because the tension is real: reviewing a Dockerfile change properly means building
it, building from inside a container means the daemon socket, and the socket is unconditional
host root. Left implicit, someone mounts the socket to make the loop pass.

## 6. Move the symlink control from the inventory to the scratch tree

The existing precondition script measures symlinks **that already exist** in the repository.
That is the wrong location. The reviewer has a writable scratch tree by design and can create
its own — e.g. a link to `/proc/self/environ`, which reads the container's environment through
an ordinary file-read.

**The control belongs at the scratch tree, not the inventory.** An inventory of existing links
cannot constrain links created after the inventory ran.

---

## Not in this queue

The read-only repository mount itself survived review. Symlink preservation, dereference, git
worktree redirection and copy-back all terminate in EROFS. It is doing real work. What failed
was the **scope** of the two proofs, not the mechanism.
