"use client";
// Reads /api/flow-board?repo= for each wall repo, then again every minute (the
// server caches each repo's GitHub reads for 60 s, so this never fans out).
// A failed or malformed response is null for that repo: the wall shows it as
// unavailable with a reason, never as zero open PRs.
import { useEffect, useState } from "react";
import { parseRepoTruth } from "@/lib/control/card-truth";
import type { RepoBoard } from "@/lib/control/command-wall";
import { parseFlowBoardPayload } from "@/lib/control/flowBoard";

export const REPO_BOARD_INTERVAL_MS = 60_000;

export type RepoBoardRead = { board: RepoBoard | null; reason: string | null };

export function parseRepoBoard(raw: unknown): RepoBoard | null {
  const board = parseFlowBoardPayload(raw);
  const truth = parseRepoTruth(raw);
  if (!board || !truth) return null;
  return { ...board, repo: truth.repo, pull_requests: truth.pull_requests, ci: truth.ci };
}

/** A read slower than this gives up, so a stalled request never outlives its poll. */
export const REPO_BOARD_TIMEOUT_MS = 20_000;

export async function readBoard(repo: string, signal: AbortSignal): Promise<RepoBoardRead> {
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, REPO_BOARD_TIMEOUT_MS);
  const onAbort = () => ctrl.abort();
  signal.addEventListener("abort", onAbort);
  try {
    const res = await fetch(`/api/flow-board?repo=${encodeURIComponent(repo)}`, { cache: "no-store", signal: ctrl.signal });
    if (!res.ok) return { board: null, reason: `flow board HTTP ${res.status}` };
    const board = parseRepoBoard(await res.json());
    return board ? { board, reason: null } : { board: null, reason: "flow board payload was not readable" };
  } catch {
    return { board: null, reason: timedOut ? "flow board timed out" : "flow board unreachable" };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  }
}

export function useRepoBoards(repos: readonly string[]): Record<string, RepoBoardRead> {
  const [reads, setReads] = useState<Record<string, RepoBoardRead>>({});
  const key = repos.join("\n");
  useEffect(() => {
    const ctrl = new AbortController();
    const run = () => {
      for (const repo of key.split("\n").filter(Boolean)) {
        void readBoard(repo, ctrl.signal).then((read) => {
          if (!ctrl.signal.aborted) setReads((prev) => ({ ...prev, [repo]: read }));
        });
      }
    };
    run();
    const timer = setInterval(run, REPO_BOARD_INTERVAL_MS);
    return () => { ctrl.abort(); clearInterval(timer); };
  }, [key]);
  return reads;
}
