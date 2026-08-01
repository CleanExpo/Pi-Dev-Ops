#!/usr/bin/env python3
"""scope_cc.py — per-capability port scope for the command-centre migration.

Separates hand-written code from generated types and CSS, because a 15,000-line
generated Supabase types file is a `supabase gen types` command, not a port.
Read-only: walks import specifiers, counts lines, writes nothing.
"""
import os
import re

W = r"D:\Authority-Site\apps\web\src"
CC = os.path.join(W, "app", "(founder)", "founder", "command-centre")
IMP = re.compile(r"""from\s+['"]([^'"]+)['"]""")
GEN = re.compile(r"(database\.ts$|\.generated\.|__generated__|supabase/types)")
CAPS = ["operator-gateway", "operations", "providers",
        "wiki-graph", "knowledge", "hermes-control-panel"]


def resolve(spec, frm):
    if spec.startswith("@/"):
        base = os.path.join(W, spec[2:].replace("/", os.sep))
    elif spec.startswith("."):
        base = os.path.normpath(os.path.join(os.path.dirname(frm), spec))
    else:
        return None
    for c in (base + ".ts", base + ".tsx",
              os.path.join(base, "index.ts"), os.path.join(base, "index.tsx"), base):
        if os.path.isfile(c):
            return c
    return None


def closure(seed_dir):
    seeds = [os.path.join(dp, f) for dp, _, fs in os.walk(seed_dir)
             for f in fs if f.endswith((".ts", ".tsx"))]
    seen, q = set(), list(seeds)
    while q:
        f = q.pop()
        if f in seen or not os.path.isfile(f):
            continue
        seen.add(f)
        try:
            src = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for s in IMP.findall(src):
            r = resolve(s, f)
            if r and r not in seen:
                q.append(r)
    return seen


def L(f):
    try:
        return sum(1 for _ in open(f, encoding="utf-8", errors="ignore"))
    except Exception:
        return 0


def norm(f):
    return f.replace(os.sep, "/")


def split(files):
    gen = sum(L(f) for f in files if GEN.search(norm(f)))
    css = sum(L(f) for f in files if f.endswith(".css"))
    tot = sum(L(f) for f in files)
    return tot, gen, css, tot - gen - css


def main():
    cl = {c: closure(os.path.join(CC, c)) for c in CAPS
          if os.path.isdir(os.path.join(CC, c))}
    shared = set(f for f in set().union(*cl.values())
                 if sum(1 for c in cl if f in cl[c]) > 1)

    print(f"{'capability':<24}{'files':>6}{'total':>9}{'generated':>11}{'css':>8}{'REAL':>9}")
    print("-" * 67)
    rows = []
    for c in cl:
        u = cl[c] - shared
        tot, gen, css, real = split(u)
        rows.append((c, len(u), tot, gen, css, real))
    for c, n, tot, gen, css, real in sorted(rows, key=lambda r: r[5]):
        print(f"{c:<24}{n:>6}{tot:>9,}{gen:>11,}{css:>8,}{real:>9,}")
    print("-" * 67)
    unique_real = sum(r[5] for r in rows)
    stot, sgen, scss, sreal = split(shared)
    print(f"{'SHARED CORE':<24}{len(shared):>6}{stot:>9,}{sgen:>11,}{scss:>8,}{sreal:>9,}")
    print()
    print(f"  hand-written code to port : {unique_real + sreal:,} lines")
    print(f"  generated (regenerate, do not port): {sgen + sum(r[3] for r in rows):,} lines")
    print(f"  css (port verbatim)       : {scss + sum(r[4] for r in rows):,} lines")


if __name__ == "__main__":
    main()
