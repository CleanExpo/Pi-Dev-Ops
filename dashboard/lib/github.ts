// lib/github.ts — GitHub API client: repo context fetching, branch + PR management

import { Octokit } from "@octokit/rest";

const SKIP_DIRS = new Set(["node_modules", ".git", ".next", "out", "dist", "build", "__pycache__"]);
const SKIP_EXT = new Set([".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz"]);
const MAX_FILE_BYTES = 40_000; // truncate files larger than this

export function makeOctokit(token: string) {
  return new Octokit({ auth: token });
}

export function parseRepoUrl(url: string): { owner: string; repo: string } {
  const match = url.match(/github\.com[/:]([\w.-]+)\/([\w.-]+?)(?:\.git)?(?:\/.*)?$/);
  if (!match) throw new Error(`Cannot parse GitHub URL: ${url}`);
  return { owner: match[1], repo: match[2] };
}

export async function getDefaultBranch(octokit: Octokit, owner: string, repo: string): Promise<string> {
  const { data } = await octokit.repos.get({ owner, repo });
  return data.default_branch;
}

export async function createBranch(
  octokit: Octokit,
  owner: string,
  repo: string,
  branchName: string,
  fromBranch: string
): Promise<void> {
  const { data: ref } = await octokit.git.getRef({
    owner, repo, ref: `heads/${fromBranch}`,
  });
  try {
    await octokit.git.createRef({
      owner, repo,
      ref: `refs/heads/${branchName}`,
      sha: ref.object.sha,
    });
  } catch (err: unknown) {
    if ((err as { status?: number }).status === 422) return; // branch already exists — reuse it
    throw err;
  }
}

export interface RepoFile {
  path: string;
  content: string;
  size: number;
}

export async function fetchRepoContext(
  octokit: Octokit,
  owner: string,
  repo: string,
  branch: string
): Promise<RepoFile[]> {
  const { data: tree } = await octokit.git.getTree({
    owner, repo, tree_sha: branch, recursive: "1",
  });

  const files = tree.tree.filter((node) => {
    if (node.type !== "blob" || !node.path) return false;
    const parts = node.path.split("/");
    if (parts.some((p) => SKIP_DIRS.has(p))) return false;
    const ext = "." + (node.path.split(".").pop() ?? "");
    if (SKIP_EXT.has(ext)) return false;
    return true;
  });

  // Prioritise high-value files, cap total at 60 files
  const priority = ["README", "package.json", "pyproject.toml", "requirements.txt",
    "tsconfig", ".env.example", "Dockerfile", "CLAUDE.md", "main.py", "index.ts"];
  files.sort((a, b) => {
    const ap = priority.findIndex((p) => (a.path ?? "").includes(p));
    const bp = priority.findIndex((p) => (b.path ?? "").includes(p));
    return (ap === -1 ? 999 : ap) - (bp === -1 ? 999 : bp);
  });
  const capped = files.slice(0, 60);

  const results = await Promise.allSettled(
    capped.map(async (node): Promise<RepoFile> => {
      const { data } = await octokit.git.getBlob({
        owner, repo, file_sha: node.sha!,
      });
      const raw = Buffer.from(data.content, "base64").toString("utf-8");
      const content = raw.length > MAX_FILE_BYTES
        ? raw.slice(0, MAX_FILE_BYTES) + `\n... [truncated ${raw.length - MAX_FILE_BYTES} bytes]`
        : raw;
      return { path: node.path!, content, size: raw.length };
    })
  );

  return results
    .filter((r): r is PromiseFulfilledResult<RepoFile> => r.status === "fulfilled")
    .map((r) => r.value);
}

export async function pushFile(
  octokit: Octokit,
  owner: string,
  repo: string,
  branch: string,
  path: string,
  content: string,
  message: string
): Promise<void> {
  let sha: string | undefined;
  try {
    const { data } = await octokit.repos.getContent({ owner, repo, path, ref: branch });
    if (!Array.isArray(data)) sha = data.sha;
  } catch {
    // file doesn't exist yet — that's fine
  }
  await octokit.repos.createOrUpdateFileContents({
    owner, repo, path, branch, message,
    content: Buffer.from(content).toString("base64"),
    ...(sha ? { sha } : {}),
  });
}

export async function createPR(
  octokit: Octokit,
  owner: string,
  repo: string,
  head: string,
  base: string,
  title: string,
  body: string
): Promise<string> {
  const { data } = await octokit.pulls.create({ owner, repo, head, base, title, body });
  return data.html_url;
}
