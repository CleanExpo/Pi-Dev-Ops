#!/usr/bin/env python3
"""assert_image_digest.py — Control 4 (PROPOSAL §9.6.1): reviewer image identity.

Resolves the digest of the image about to be used and compares it to the authorised set in
docker/reviewer/image.manifest.json. FAILS CLOSED on anything unrecognised: an unknown digest
is a failure, not a warning. Same posture as the codex-config hash it is modelled on
(codex-review.sh:85-87) — exclude known churn, fail on everything else.

    python scripts/assert_image_digest.py [--image REF] [--manifest PATH] [--quiet]

Exit: 0 authorised · 1 digest not authorised · 2 could not determine (fail closed).

Print the resolved digest into the review transcript so a finding is bound to the image that
produced it, the way it is already bound to HEAD.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO / "docker" / "reviewer" / "image.manifest.json"


def resolve_digest(ref: str) -> str:
    """Content digest of a local image. Fails closed if docker or the image is unavailable."""
    try:
        r = subprocess.run(["docker", "image", "inspect", ref, "--format", "{{.Id}}"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  [FAIL-CLOSED] cannot run docker: {exc}", file=sys.stderr)
        sys.exit(2)
    if r.returncode != 0:
        print(f"  [FAIL-CLOSED] image not resolvable: {ref}\n    {r.stderr.strip()[:200]}",
              file=sys.stderr)
        sys.exit(2)
    digest = r.stdout.strip()
    if not digest.startswith("sha256:"):
        print(f"  [FAIL-CLOSED] unexpected digest form: {digest!r}", file=sys.stderr)
        sys.exit(2)
    return digest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", default=None, help="image ref (default: manifest 'reference')")
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    mpath = Path(args.manifest)
    if not mpath.is_file():
        print(f"  [FAIL-CLOSED] manifest missing: {mpath}", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  [FAIL-CLOSED] manifest unparseable: {exc}", file=sys.stderr)
        return 2

    authorised = {e["digest"] for e in manifest.get("authorised_digests", []) if e.get("digest")}
    if not authorised:
        print("  [FAIL-CLOSED] manifest lists no authorised digests", file=sys.stderr)
        return 2

    ref = args.image or manifest.get("reference")
    if not ref:
        print("  [FAIL-CLOSED] no image reference given and none in manifest", file=sys.stderr)
        return 2

    actual = resolve_digest(ref)
    if not args.quiet:
        print(f"  image     : {ref}")
        print(f"  digest    : {actual}")
        print(f"  authorised: {len(authorised)} digest(s) in {mpath.name}")

    if actual in authorised:
        print(f"  ==== CONTROL 4 PASS - image digest authorised")
        print(f"       record this digest beside HEAD in the review evidence")
        return 0

    print(f"\n  ==== CONTROL 4 FAIL - IMAGE DIGEST NOT AUTHORISED")
    print(f"       ref      {ref}")
    print(f"       actual   {actual}")
    print(f"       expected one of:")
    for d in sorted(authorised):
        print(f"         {d}")
    print("       An unrecognised image is a REFUSAL, not a warning: the suite would run on an")
    print("       unknown toolchain and the review would be unreproducible. Rotate the pin in")
    print("       the manifest with a reason, or use the authorised image.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
