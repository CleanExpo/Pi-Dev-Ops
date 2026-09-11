"use client";

import Link from "next/link";
import {
  WATCH_BUILDS,
  WATCH_LOOP,
  WATCH_SWARM,
  watchBuildsHref,
  watchLoopHref,
  watchSwarmHref,
} from "@/lib/control/watchWork";

export default function LiveWatchLinks({ hasPr }: { hasPr: boolean }) {
  return (
    <nav
      aria-label="Watch the work"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted"
    >
      <Link href={watchBuildsHref()} className="text-cyan-400 hover:underline">
        {WATCH_BUILDS}
      </Link>
      <span>session logs</span>
      <Link href={watchSwarmHref()} className="text-cyan-400 hover:underline">
        {WATCH_SWARM}
      </Link>
      <span>{hasPr ? "PR in flight — kill lives here" : "PRs and kill"}</span>
      <Link href={watchLoopHref()} className="text-cyan-400 hover:underline">
        {WATCH_LOOP}
      </Link>
      <span>queue and poller</span>
    </nav>
  );
}
