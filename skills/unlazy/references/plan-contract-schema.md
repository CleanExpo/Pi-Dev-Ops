# Executable Plan and Ownership Contract

Load this schema when creating, validating, or amending an Unlazy plan. `PLAN.json` is the normative
input to `python scripts/unlazy_plan.py`; it is one flat JSON object with a `nodes` array.

## PLAN.json 1.0

```json
{
  "schema_version": "1.0",
  "plan_id": "uuid",
  "task": "verbatim task",
  "requested_depth": 5,
  "effective_depth": 4,
  "adjustment_reason": "natural joints stop at depth four",
  "base_sha": "git-sha",
  "worktree": "/absolute/isolated/path",
  "max_parallel_workers": 3,
  "nodes": [
    {
      "id": "1.1",
      "type": "leaf",
      "purpose": "bounded outcome",
      "owns": ["src/a.py", "tests/test_a.py"],
      "needs": [],
      "exports": ["InterfaceName", "schema:v1"],
      "route_ref": "route-id",
      "gates": "gates/leaf-1.1.md",
      "state": "pending",
      "attempt": 0
    },
    {
      "id": "1",
      "type": "root",
      "purpose": "integrate and verify",
      "owns": [],
      "needs": ["1.1"],
      "exports": [],
      "route_ref": "",
      "gates": "gates/root.md",
      "state": "pending",
      "attempt": 0
    }
  ]
}
```

Required top-level fields are `schema_version`, `plan_id`, `task`, `requested_depth`,
`effective_depth`, and a non-empty `nodes` array. `max_parallel_workers` defaults to three.
`adjustment_reason` is required when effective and requested depth differ. `base_sha` and `worktree`
are accepted provenance fields but the current linter permits them to be empty; the driver must
populate them before dispatch.

Each node requires a non-empty unique `id`, `type` in `root|branch|leaf`, and list values for `owns`,
`needs`, and `exports`. `state` defaults to `pending`; `attempt` defaults to zero. A leaf must own at
least one relative non-wildcard path and name a gate file. Exactly one root is required.

## Executable commands

Run from the repository root:

```bash
python scripts/unlazy_plan.py template "<verbatim task>" --tree 5 --max-workers 3
python scripts/unlazy_plan.py lint PLAN.json
python scripts/unlazy_plan.py ready PLAN.json --active 1.1
```

`template` prints a plan shell that still contains `REPLACE_ME`; replace it before `lint`. `lint`
prints `{"status":"valid",...}` only after the current executable validations pass. `ready` prints
the next deterministic leaf IDs, excluding supplied `--active` IDs and respecting the worker cap.

## Current CLI enforcement

The current linter rejects:

- schema versions other than `1.0`, missing task/plan ID, invalid depths, effective depth above
  requested depth or seven, and worker caps outside one through sixteen;
- missing/duplicate node IDs, invalid types/states/attempts, unknown/self dependencies, and cycles;
- plans without exactly one root;
- leaf nodes without owned paths or a gate file;
- absolute, parent-traversing, wildcard, exact, or parent/child ownership overlaps across any nodes.

Accepted ownership paths are stored in canonical repository-relative POSIX form (for example,
`./src/a.py` becomes `src/a.py`) before collision and returned-diff checks use them.

The current `ready` command selects only pending/ready leaves whose dependencies are passed. It does
not execute workers, gates, integrations, reservations, or providers.

## Driver-enforced contract

Before dispatch, the driver additionally freezes exact production/test/docs/generated paths,
exports and shared interfaces, data/migration ownership, naming/error/security conventions,
approved tools, forbidden paths, root outcomes, sensitivity, spend/time caps, gate digest, and
contract digest. These may live in a signed sidecar/receipt until the executable schema formally
adds them.

The current CLI does **not** validate root reachability, disconnected nodes, leaf childlessness,
shared-interface semantics, base cleanliness, root outcomes, cost reservations, contract digests,
or exact-SHA receipts. Unknown extra JSON fields are not proof that the runtime enforces them. The
driver/verifier must check them separately and must not present a successful `lint` as full
completion evidence.

## Ownership and amendment rules

1. Give every path one node owner under the current strict overlap check; shared files belong only
   to an integration node.
2. Workers return proposed shared-interface changes instead of editing outside `owns`.
3. The verifier compares the candidate diff with `owns`; any outside path fails the leaf.
4. Concurrent mutation defaults to isolated worktrees. Shared-folder work requires disjoint paths
   plus return-time diff validation.
5. A moving/dirty base or contract change invalidates affected routes and gates; re-freeze, reroute,
   and rerun.

Executable plan validation passes only when `lint` exits zero. Full contract readiness additionally
requires the driver-enforced checks above before any dispatch.
