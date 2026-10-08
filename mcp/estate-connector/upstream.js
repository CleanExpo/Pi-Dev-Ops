import { redact, trimHealth, trimLive } from "./shape.js";

export async function fetchJson(fetchImpl, url, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), options.timeoutMs || 4000);
  try {
    const res = await fetchImpl(url, {
      method: options.method || "GET",
      headers: options.headers,
      body: options.body,
      signal: ctrl.signal,
      redirect: "manual",
    });
    const text = await res.text();
    let body = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = { unparsed: true };
      }
    }
    return { ok: Boolean(res.ok), status: res.status, body, error: res.ok ? null : "http_error" };
  } catch (err) {
    const name = err && err.name;
    return { ok: false, status: 0, body: null, error: name === "AbortError" || name === "TimeoutError" ? "timeout" : "unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

function piceoHeaders(config) {
  const headers = { Accept: "application/json" };
  if (config.piceoBearer) headers.Authorization = `Bearer ${config.piceoBearer}`;
  return headers;
}

export async function piceoHealth(config, fetchImpl) {
  if (!config.piceoBaseUrl) return { configured: false, error: config.piceoBaseUrlError };
  const url = `${config.piceoBaseUrl}/health`;
  const res = await fetchJson(fetchImpl, url, { headers: piceoHeaders(config) });
  return {
    configured: true,
    url,
    http_status: res.status,
    bearer_configured: Boolean(config.piceoBearer),
    body: trimHealth(res.body),
    error: res.error,
  };
}

export async function missionControlLive(config, fetchImpl) {
  if (!config.piceoBaseUrl) return { configured: false, error: config.piceoBaseUrlError };
  const url = `${config.piceoBaseUrl}/api/mission-control/live`;
  const res = await fetchJson(fetchImpl, url, { headers: piceoHeaders(config) });
  return {
    configured: true,
    url,
    http_status: res.status,
    bearer_configured: Boolean(config.piceoBearer),
    body: res.ok ? trimLive(res.body) : null,
    error: res.ok ? null : (res.error || "unavailable"),
    note: res.ok ? null : "The live route wants a dashboard session. The Linear queue below is the same queue Mission Control reads when LINEAR_API_KEY is set.",
  };
}

function githubUrl(repo, suffix = "") {
  const [owner, name] = repo.split("/");
  return `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}${suffix}`;
}

export async function githubStatus(config, fetchImpl, repo) {
  if (!config.githubToken) return { configured: false, repo };
  const headers = {
    Authorization: `Bearer ${config.githubToken}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "estate-connector-mcp",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const [repoRes, runsRes] = await Promise.all([
    fetchJson(fetchImpl, githubUrl(repo), { headers }),
    fetchJson(fetchImpl, githubUrl(repo, "/actions/runs?per_page=5"), { headers }),
  ]);
  if (!repoRes.ok) return { configured: true, reachable: false, repo, http_status: repoRes.status };
  const body = repoRes.body || {};
  const runs = Array.isArray(runsRes.body?.workflow_runs) ? runsRes.body.workflow_runs : [];
  return {
    configured: true,
    reachable: true,
    repo: body.full_name || repo,
    default_branch: body.default_branch || null,
    pushed_at: body.pushed_at || null,
    open_issues_count: body.open_issues_count ?? null,
    visibility: body.visibility || null,
    recent_runs: runs.slice(0, 5).map((run) => ({
      name: run.name || null,
      conclusion: run.conclusion || null,
      status: run.status || null,
      url: run.html_url || null,
      created_at: run.created_at || null,
    })),
  };
}

export async function linearReady(config, fetchImpl, projectIds) {
  if (!config.linearKey) return { configured: false, issues: [] };
  const query = `query($name: String!) {
    issues(first: 25, filter: { state: { name: { eq: $name } } }) {
      nodes { identifier title priority url project { id name } state { name } }
    }
  }`;
  const res = await fetchJson(fetchImpl, "https://api.linear.app/graphql", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: config.linearKey },
    body: JSON.stringify({ query, variables: { name: "Ready for Pi-Dev" } }),
  });
  if (!res.ok || res.body?.errors) return { configured: true, reachable: false, issues: [] };
  const nodes = Array.isArray(res.body?.data?.issues?.nodes) ? res.body.data.issues.nodes : [];
  const allow = new Set(projectIds.filter(Boolean));
  const issues = nodes
    .filter((node) => allow.has(node?.project?.id))
    .slice(0, 20)
    .map((node) => ({
      identifier: node.identifier || null,
      title: String(node.title || "").slice(0, 140),
      priority: node.priority ?? null,
      url: node.url || null,
      project_id: node.project?.id || null,
      project_name: node.project?.name || null,
      state: node.state?.name || null,
    }));
  return { configured: true, reachable: true, issues: redact(issues) };
}

export async function probeUrls(fetchImpl, rows) {
  const slice = rows.slice(0, 8);
  const checked = [];
  for (const row of slice) {
    const res = await fetchJson(fetchImpl, row.url, { timeoutMs: 3000, headers: { Accept: "text/plain" } });
    checked.push({ ...row, http_status: res.status, error: res.error });
  }
  return { checked, truncated: rows.length > slice.length };
}
