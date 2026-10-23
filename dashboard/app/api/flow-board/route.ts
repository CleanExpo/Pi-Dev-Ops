import { NextResponse } from "next/server";
import { assembleFlowBoard, emptyFlowBoard, rowFromPull } from "@/lib/control/flowBoard";
import { registryRepo } from "@/lib/control/registry-repos";
import { readRepo, type GhPull } from "@/lib/control/repo-truth-server";

export const dynamic = "force-dynamic";

const DEFAULT_REPO = "CleanExpo/Pi-Dev-Ops";

function boardRows(pulls: GhPull[]) {
  const now = Date.now();
  return pulls
    .filter((pull) => (
      Number.isInteger(pull.number)
      && pull.number > 0
      && typeof pull.html_url === "string"
      && typeof pull.created_at === "string"
      && !Number.isNaN(Date.parse(pull.created_at))
    ))
    .map((pull) => rowFromPull({
      id: `PR-${pull.number}`,
      title: typeof pull.title === "string" ? pull.title.slice(0, 160) : "",
      url: pull.html_url,
      paths: [],
      labels: (pull.labels ?? [])
        .map((item) => item.name)
        .filter((name): name is string => typeof name === "string"),
      createdAt: pull.created_at,
      mergedToday: false,
      auditGreen: false,
      nowMs: now,
    }));
}

/**
 * Open PRs and default-branch CI for one registered project. `?repo=` must be a
 * repo in the project registry; anything else is refused before GitHub is called.
 * With no `?repo=` it serves the Pi-Dev-Ops board, as it always has.
 */
export async function GET(request: Request) {
  const asked = new URL(request.url).searchParams.get("repo");
  const repo = asked === null ? DEFAULT_REPO : registryRepo(asked);
  if (!repo) {
    return NextResponse.json({ error: "repo is not a registered project" }, { status: 400 });
  }
  const { pulls, ci } = await readRepo(repo);
  const board = pulls.status === "ok"
    ? assembleFlowBoard(boardRows(pulls.value.rows), null)
    : emptyFlowBoard(`GitHub unavailable: ${pulls.reason}`, false);
  const pullRequests = pulls.status === "ok"
    ? { status: "ok" as const, value: { count: pulls.value.count, capped: pulls.value.capped } }
    : pulls;
  return NextResponse.json({ ...board, repo, pull_requests: pullRequests, ci });
}
