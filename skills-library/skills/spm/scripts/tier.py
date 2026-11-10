#!/usr/bin/env python3
"""The /spm tier, computed instead of read from prose (references/leveling.md §2).

WHY. Review round 2 (18/10/2026) found two holes in the prose rules: F=0,I=0,N=0,X=0,S=1
matched no tier at all, and an operator pin such as "bench=T0" could drop the mandatory
security seat on an auth change. Rules evaluated in order, with T1 as the catch-all, cover
all 243 axis combinations by construction; the test enumerates them.

    tier.py F I N X S [--pin T0..T3]     # each axis 0..2
    prints: T<n> [pinned|floor-kept]

Stdlib only.
"""
import sys

TIERS = ("T0", "T1", "T2", "T3")


def tier(f: int, i: int, n: int, x: int, s: int) -> str:
    axes = (f, i, n, x, s)
    if any(a not in (0, 1, 2) for a in axes):
        raise ValueError("every axis is 0, 1 or 2")
    total = sum(axes)
    if total >= 7 or i == 2 or s == 2 or (n == 2 and x == 2):
        return "T3"
    if 4 <= total <= 6 or 2 in axes:
        return "T2"
    if total <= 1 and i == 0 and s == 0:
        return "T0"
    return "T1"  # everything else, including sum 1 carried by I or S


def floor(axes) -> str:
    """The lowest tier a pin may reach. T2 and T3 carry mandatory seats (the judge seat; the
    adversarial pass), so a computed T2/T3 is its own floor; below that, any irreversibility or
    security signal keeps T1 (review rounds 2 and 3)."""
    computed = tier(*axes)
    if computed in ("T2", "T3"):
        return computed
    return "T1" if axes[1] or axes[4] else "T0"


def effective(axes, pin=None):
    computed = tier(*axes)
    if pin is None:
        return computed, ""
    if pin not in TIERS:
        raise ValueError(f"pin must be one of {TIERS}")
    low = floor(axes)
    if TIERS.index(pin) < TIERS.index(low):
        return low, "floor-kept"
    return pin, "pinned"


def main(argv) -> int:
    pin = None
    if "--pin" in argv:
        k = argv.index("--pin")
        if k + 1 >= len(argv):
            print("tier.py: --pin needs a tier", file=sys.stderr)
            return 2
        pin = argv[k + 1]
        argv = argv[:k] + argv[k + 2:]
    try:
        axes = tuple(int(a) for a in argv)
        if len(axes) != 5:
            raise ValueError("give five axes: F I N X S")
        t, note = effective(axes, pin)
    except ValueError as e:
        print(f"tier.py: {e}", file=sys.stderr)
        return 2
    print(f"{t} {note}".strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
