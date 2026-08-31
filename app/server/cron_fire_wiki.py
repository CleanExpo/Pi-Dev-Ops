"""cron_fire_wiki.py — scheduled ticks for the knowledge front door (M4/M6).

Two handlers, the same shape as `cron_fire_mesh.py`:

  staging_pull        — drain `wiki_source_staging` into `Sources/`, which is
                        what turns an upload from anywhere into a file the
                        Librarian will ingest on its normal cycle.
  youtube_transcripts — run the transcript producer, which writes `Sources/*.md`
                        from the strategically-scored catalog.

BOTH ARE GATED OFF and both stay useless until a human acts, deliberately:

  * `staging_pull` only does work on the machine that holds the vault. On a
    cloud container `_sources_dir()` points at a path that does not exist, so
    the gate is what stops it writing files into a container that will be
    reclaimed.
  * `youtube_transcripts` has no input until YouTube OAuth is granted or a
    Takeout export is dropped (switch #6 in docs/runbooks/fleet-operations.md).
    Until then it reports considered=0, which is correct and not an error.

A disabled tick LOGS AND RETURNS rather than raising. A deliberate off switch is
not a trigger failure, and raising here would blank `last_fired_at` and set off
the cron watchdog — the same reasoning as the mesh dispatcher.
"""
import asyncio
import os

_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(name: str) -> bool:
    """Read the switch per call so it can be flipped without a redeploy."""
    return os.environ.get(name, "").strip().lower() in _TRUTHY


async def _fire_staging_pull_trigger(trigger: dict, log) -> None:
    """Drain queued uploads onto the brain host's `Sources/` directory.

    Runs in a worker thread: the drain is blocking Supabase I/O plus filesystem
    writes, and the cron loop is the server's event loop.
    """
    if not _enabled("WIKI_STAGING_PULL_ENABLED"):
        log.info("staging_pull id=%s skipped — WIKI_STAGING_PULL_ENABLED not set", trigger["id"])
        return
    from swarm.sources_watcher import pull_staging  # noqa: PLC0415

    result = await asyncio.to_thread(pull_staging)
    log.info(
        "staging_pull id=%s written=%d quarantined=%d errors=%d",
        trigger["id"], len(result.written), len(result.quarantined), len(result.errors),
    )
    for sid in result.quarantined:
        log.warning("staging_pull → quarantined %s (filename failed re-validation)", sid)
    for err in result.errors:
        log.warning("staging_pull → error %s", err)


async def _fire_youtube_transcripts_trigger(trigger: dict, log) -> None:
    """Fetch captions for catalogued videos into `Sources/*.md`."""
    if not _enabled("YOUTUBE_TRANSCRIPTS_ENABLED"):
        log.info(
            "youtube_transcripts id=%s skipped — YOUTUBE_TRANSCRIPTS_ENABLED not set",
            trigger["id"],
        )
        return
    # `sources_dir` is owned by youtube_transcript_state; youtube_transcripts
    # imports it under an alias. Import it from its owner rather than through
    # that alias, so a rename over there is a hard failure here instead of a
    # tick that silently writes into the wrong directory.
    from scripts.youtube_transcript_state import sources_dir  # noqa: PLC0415
    from scripts.youtube_transcripts import run  # noqa: PLC0415

    limit = int(trigger.get("limit") or 10)
    # `limit` is keyword-only on run(); passing it positionally is a TypeError.
    result = await asyncio.to_thread(lambda: run(sources_dir(), limit=limit))
    log.info(
        "youtube_transcripts id=%s considered=%d written=%d no_captions=%d failed=%d",
        trigger["id"], result.considered, len(result.written),
        len(result.no_captions), len(result.failed),
    )
