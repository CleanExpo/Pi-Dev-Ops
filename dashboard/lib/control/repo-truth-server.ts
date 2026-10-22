// Server-only GitHub reads for a project card: open PRs and default-branch CI.
//
// One request per field (REST pulls, GraphQL status rollup), cached per repo for
// CACHE_MS so a page of cards cannot fan out into repeated calls. Each field
// reports its own failure as `unavailable` with a reason; nothing polls.
import type { CiState, CiValue, Field, PullsValue } from "@/lib/control/card-truth";

export interface GhPull {
  number: number;
  title: string;
  html_url: string;
  created_at: string;
  labels?: Array<{ name: string }>;
}

export interface RepoReads {
  pulls: Field<{ rows: GhPull[] } & PullsValue>;
  ci: Field<CiValue>;
}

const CACHE_MS = 60_000;
const PER_PAGE = 30;
const cache = new Map<string, { at: number; reads: Promise<RepoReads> }>();

const CI_QUERY = `query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
defaultBranchRef{name target{... on Commit{oid statusCheckRollup{state}}}}}}`;

const down = (reason: string) => ({ status: "unavailable" as const, reason });

export function resetRepoTruthCache(): void {
  cache.clear();
}

async function readPulls(repo: string, token: string): Promise<RepoReads["pulls"]> {
  const res = await fetch(`https://api.github.com/repos/${repo}/pulls?state=open&per_page=${PER_PAGE}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }, cache: "no-store",
  });
  if (!res.ok) return down(`GitHub pulls HTTP ${res.status}`);
  const body: unknown = await res.json();
  if (!Array.isArray(body)) return down("GitHub pulls: unexpected payload");
  return { status: "ok", value: { rows: body as GhPull[], count: body.length, capped: body.length >= PER_PAGE } };
}

async function readCi(repo: string, token: string): Promise<Field<CiValue>> {
  const [owner, name] = repo.split("/");
  const res = await fetch("https://api.github.com/graphql", {
    method: "POST", cache: "no-store",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query: CI_QUERY, variables: { owner, name } }),
  });
  if (!res.ok) return down(`GitHub CI HTTP ${res.status}`);
  const body = (await res.json()) as {
    data?: { repository?: { defaultBranchRef?: { name?: string; target?: { oid?: string; statusCheckRollup?: { state?: string } | null } } | null } | null };
    errors?: Array<{ message?: string }>;
  };
  if (body.errors?.length) return down(`GitHub CI read failed: ${body.errors[0]?.message ?? "unknown error"}`);
  const ref = body.data?.repository?.defaultBranchRef;
  if (!ref?.name || !ref.target?.oid) return down("GitHub CI: no default branch commit");
  const rollup = ref.target.statusCheckRollup;
  const state = (rollup ? String(rollup.state ?? "").toLowerCase() : "none") as CiState;
  if (!["success", "failure", "error", "pending", "expected", "none"].includes(state)) return down(`GitHub CI: unknown state ${state}`);
  return { status: "ok", value: { branch: ref.name, sha: ref.target.oid, state } };
}

async function settle<T>(read: Promise<Field<T>>, label: string): Promise<Field<T>> {
  try {
    return await read;
  } catch {
    return down(`GitHub ${label} unreachable`);
  }
}

/** Both card fields for a registry-validated repo; cached per repo for CACHE_MS. */
export function readRepo(repo: string): Promise<RepoReads> {
  const token = process.env.GITHUB_TOKEN?.trim();
  if (!token) return Promise.resolve({ pulls: down("GITHUB_TOKEN not set"), ci: down("GITHUB_TOKEN not set") });
  const hit = cache.get(repo);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.reads;
  const reads = Promise.all([settle(readPulls(repo, token), "pulls"), settle(readCi(repo, token), "CI")])
    .then(([pulls, ci]) => ({ pulls, ci }));
  cache.set(repo, { at: Date.now(), reads });
  return reads;
}
