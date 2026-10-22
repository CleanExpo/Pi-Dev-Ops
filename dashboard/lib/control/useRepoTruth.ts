"use client";
// Reads /api/flow-board?repo= once per distinct repo when the card list changes.
// No polling: the server caches GitHub reads, and a reload re-reads. A failed or
// malformed response becomes UNAVAILABLE for both fields, with the reason.
import { useEffect, useState } from "react";
import { parseRepoTruth, unavailableTruth, type RepoTruth } from "@/lib/control/card-truth";

async function readTruth(repo: string): Promise<RepoTruth> {
  try {
    const res = await fetch(`/api/flow-board?repo=${encodeURIComponent(repo)}`, { cache: "no-store" });
    if (!res.ok) return unavailableTruth(repo, `flow board HTTP ${res.status}`);
    return parseRepoTruth(await res.json()) ?? unavailableTruth(repo, "flow board payload was not card truth");
  } catch {
    return unavailableTruth(repo, "flow board unreachable");
  }
}

export function useRepoTruth(repos: string[]): Record<string, RepoTruth> {
  const [truth, setTruth] = useState<Record<string, RepoTruth>>({});
  const key = [...new Set(repos)].sort().join("\n");
  useEffect(() => {
    let live = true;
    for (const repo of key ? key.split("\n") : []) {
      void readTruth(repo).then((value) => {
        if (live) setTruth((prev) => ({ ...prev, [repo]: value }));
      });
    }
    return () => { live = false; };
  }, [key]);
  return truth;
}
