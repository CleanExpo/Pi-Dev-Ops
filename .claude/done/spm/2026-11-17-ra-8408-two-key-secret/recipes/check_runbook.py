"""AC-13: the runbook and the two docs say what the spec requires. Run from the repo root."""
import sys

RUNBOOK = "docs/runbooks/fleet-key-rotation.md"
MUST = [
    "step 0", "step 1", "step 2", "step 3", "step 4", "step 5", "step 6",
    "what you should see", "how to stop",
    "how often it calls", "confirmed", "n8n", "routine-complete", "unknown",
    "caller-side success", "is unknown, not quiet",
    "only then remove", "one combined change", "ignore that line",
    "roll forward only", "never press railway rollback",
    "note the deployment", "read the start-up line from that deployment",
    "pi_ceo_webhook_secret", "tao_github_webhook_secret", "not the signing secret",
    "must be a different value", "7 days",
    "l1", "l2", "l3",
    "exposure ends only after steps 4, 5 and 6",
    "never typed as a command argument",
]
MUST_NOT = ["60 minutes"]
NEXT = "TAO_INTERNAL_WEBHOOK_SECRET_NEXT"
CURRENT = "TAO_INTERNAL_WEBHOOK_SECRET"
READ = "TAO_FLEET_READ_SECRET"


def flat(path):
    with open(path, encoding="utf-8") as fh:
        return " ".join(fh.read().split()).lower()


def main() -> int:
    bad = []
    try:
        book = flat(RUNBOOK)
    except OSError as exc:
        print("RUNBOOK_FAIL:", exc)
        return 1
    bad += [f"runbook lacks {p!r}" for p in MUST if p not in book]
    bad += [f"runbook contains {p!r}" for p in MUST_NOT if p in book]
    if book.count("how to stop") < 6:
        bad.append("fewer than 6 'how to stop' lines")
    for doc in (".env.example", "DEPLOYMENT.md"):
        try:
            with open(doc, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            bad.append(str(exc))
            continue
        if NEXT not in text:
            bad.append(f"{doc} lacks {NEXT}")
        if CURRENT not in text.replace(NEXT, ""):
            bad.append(f"{doc} lacks {CURRENT}")
        if READ not in text:
            bad.append(f"{doc} lacks {READ}")
    if bad:
        print("RUNBOOK_FAIL:\n" + "\n".join(bad))
        return 1
    print("RUNBOOK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
