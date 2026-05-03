#!/usr/bin/env node
/**
 * Pi CEO MCP Server v3.0.0 — Built on official @modelcontextprotocol/sdk
 *
 * Registered in: %APPDATA%\Claude\claude_desktop_config.json
 * Transport: stdio (JSON-RPC 2.0 via SDK — all protocol handled automatically)
 *
 * FIXES from v2.0.0:
 *   - Zod validation errors (id: undefined on notifications)
 *   - Proper MCP protocol negotiation via official SDK
 *   - inputSchema now uses Zod for runtime validation
 *
 * Tools available in Claude Desktop / CoWork:
 *   - get_last_analysis       — reads .harness/ output from last run
 *   - generate_board_notes    — formats exec summary as board meeting notes
 *   - get_sprint_plan         — returns prioritised sprint items
 *   - get_feature_list        — returns full feature JSON
 *   - list_harness_files      — shows what's in .harness/
 *   - get_zte_score           — ZTE maturity score and leverage breakdown
 *   - linear_list_issues      — list issues from Linear Pi-Dev-Ops project
 *   - linear_create_issue     — create a new issue in Linear
 *   - linear_update_issue     — update an existing Linear issue
 *   - linear_search_issues    — search issues by query text
 *   - linear_sync_board       — full board sync (all statuses)
 *   - write_obsidian_note     — write/overwrite a note in the local Obsidian vault (RA-926)
 *   - search_lessons          — keyword search over lessons.jsonl institutional memory (RA-927)
 *   - perplexity_research     — real-time CVE/dep/architecture research via Perplexity Sonar (RA-929)
 *   - run_parallel            — execute multiple read-only tools concurrently (RA-933)
 */

const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const fs   = require("fs");
const path = require("path");
const https = require("https");
const vm    = require("vm");  // RA-1458: code_execute sandbox

// ── Configuration ──────────────────────────────────────────────────────────────
const HARNESS_DIR = process.env.HARNESS_DIR
  || path.join(__dirname, "..", ".harness");

const LINEAR_API_KEY = process.env.LINEAR_API_KEY || "";
const LINEAR_API_URL = "https://api.linear.app/graphql";

// Pi-Dev-Ops project ID (from the URL slug)
const LINEAR_PROJECT_SLUG = process.env.LINEAR_PROJECT_SLUG || "pi-dev-ops";

// ── Obsidian Local REST API (RA-926) ───────────────────────────────────────────
// Requires the "Local REST API" community plugin in Obsidian.
// Set OBSIDIAN_TOKEN to the API key shown in the plugin settings.
// Set OBSIDIAN_URL to override the default (e.g. non-standard port).
const OBSIDIAN_TOKEN = process.env.OBSIDIAN_TOKEN || "";
const OBSIDIAN_BASE_URL = process.env.OBSIDIAN_URL || "https://127.0.0.1:27124";

// ── Perplexity Sonar API (RA-929) ─────────────────────────────────────────────
// Set PERPLEXITY_API_KEY in the MCP env block (claude_desktop_config.json).
// When unset, perplexity_research returns a clear error rather than failing silently.
// Models: "sonar" (fast, $0.25/M tokens), "sonar-pro" (deep research, $2.50/M tokens).
const PERPLEXITY_API_KEY = process.env.PERPLEXITY_API_KEY || "";

// ── Helpers ────────────────────────────────────────────────────────────────────
function readHarness(filename) {
  const p = path.join(HARNESS_DIR, filename);
  if (!fs.existsSync(p)) {
    return `${filename} not found in ${HARNESS_DIR}. Run an analysis first at https://dashboard-unite-group.vercel.app/dashboard`;
  }
  return fs.readFileSync(p, "utf8");
}

function linearGql(query, variables = {}) {
  return new Promise((resolve, reject) => {
    if (!LINEAR_API_KEY) {
      return reject(new Error(
        "LINEAR_API_KEY not set. Add it to your environment:\n" +
        "  Windows: setx LINEAR_API_KEY \"lin_api_...\"\n" +
        "  Or add to claude_desktop_config.json env block."
      ));
    }
    const body = JSON.stringify({ query, variables });
    const req = https.request(LINEAR_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": LINEAR_API_KEY,
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", (chunk) => data += chunk);
      res.on("end", () => {
        try {
          const json = JSON.parse(data);
          if (json.errors) {
            reject(new Error(`Linear API error: ${JSON.stringify(json.errors)}`));
          } else {
            resolve(json.data);
          }
        } catch (e) {
          reject(new Error(`Linear API parse error: ${e.message}`));
        }
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

/**
 * RA-926 — Write content to an Obsidian vault path via the Local REST API plugin.
 *
 * @param {string} vaultPath  Path relative to vault root, e.g. "Pi-CEO/2026-04-14.md"
 * @param {string} content    Markdown content to write (creates or overwrites the note)
 * @returns {Promise<void>}   Resolves on 2xx, rejects with error message otherwise
 */
function obsidianWrite(vaultPath, content) {
  return new Promise((resolve, reject) => {
    if (!OBSIDIAN_TOKEN) {
      return reject(new Error(
        "OBSIDIAN_TOKEN not set. Add it to claude_desktop_config.json env block.\n" +
        "Get the token from Obsidian → Settings → Local REST API."
      ));
    }
    // Encode each path segment but preserve slashes
    const encodedPath = vaultPath.split("/").map(encodeURIComponent).join("/");
    const urlObj = new URL(`${OBSIDIAN_BASE_URL}/vault/${encodedPath}`);
    const bodyBuf = Buffer.from(content, "utf8");
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 27124,
      path: urlObj.pathname,
      method: "PUT",
      headers: {
        "Authorization": `Bearer ${OBSIDIAN_TOKEN}`,
        "Content-Type": "text/markdown",
        "Content-Length": bodyBuf.length,
      },
      rejectUnauthorized: false, // Obsidian uses a self-signed TLS cert
    };
    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (c) => data += c);
      res.on("end", () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
        } else {
          reject(new Error(`Obsidian API ${res.statusCode}: ${data.slice(0, 200)}`));
        }
      });
    });
    req.on("error", reject);
    req.write(bodyBuf);
    req.end();
  });
}

async function findTeamId() {
  const data = await linearGql(`{ teams { nodes { id name key } } }`);
  const teams = data.teams.nodes;
  if (!teams.length) throw new Error("No teams found in Linear workspace");
  return teams[0]; // Return first team (Unite Group)
}

async function findProjectId() {
  const data = await linearGql(`{
    projects(filter: { slugId: { eq: "${LINEAR_PROJECT_SLUG}" } }) {
      nodes { id name slugId }
    }
  }`);
  if (data.projects.nodes.length > 0) return data.projects.nodes[0];

  // Fallback: search by name
  const data2 = await linearGql(`{
    projects(filter: { name: { containsIgnoreCase: "pi-dev-ops" } }) {
      nodes { id name slugId }
    }
  }`);
  if (data2.projects.nodes.length > 0) return data2.projects.nodes[0];

  // Second fallback: search more broadly
  const data3 = await linearGql(`{
    projects { nodes { id name slugId } }
  }`);
  const match = data3.projects.nodes.find(p =>
    p.name.toLowerCase().includes("pi") || p.slugId?.includes("pi")
  );
  if (match) return match;
  throw new Error(`Project "${LINEAR_PROJECT_SLUG}" not found. Available: ${data3.projects.nodes.map(p => p.name).join(", ")}`);
}

/**
 * RA-1518 gap #4 — Route Linear tickets to the correct repo's project.
 * Reads `.harness/projects.json` and returns { teamId, projectId, repo } for a
 * given project_key (matches `id` field in the JSON: "restoreassist",
 * "pi-dev-ops", "carsi", "synthex", "dr-nrpg", etc.).
 *
 * Falls through to the default Pi-Dev-Ops project when project_key is not
 * supplied or the key isn't found — so existing callers are unaffected.
 */
function resolveProjectRouting(project_key) {
  if (!project_key) return null;
  try {
    const pj = path.join(HARNESS_DIR, "projects.json");
    if (!fs.existsSync(pj)) return null;
    const data = JSON.parse(fs.readFileSync(pj, "utf8"));
    const entry = (data.projects || []).find(p => p.id === project_key);
    if (!entry) return null;
    return {
      teamId: entry.linear_team_id,
      projectId: entry.linear_project_id,
      repo: entry.repo,
      teamKey: entry.linear_team_key,
    };
  } catch (e) {
    return null;
  }
}

// ── RA-933: Parallel tool execution ─────────────────────────────────────────
// READ_ONLY_TOOLS: safe to run concurrently — no mutations, no ordering deps.
const READ_ONLY_TOOLS = new Set([
  "get_feature_list", "get_last_analysis", "get_project_health",
  "get_zte_score", "get_sprint_plan", "get_pipeline", "list_harness_files",
  "linear_list_issues", "linear_search_issues", "linear_status",
  "get_monitor_digest", "search_lessons",
]);

// Internal dispatch map for run_parallel — populated as tools are registered.
const _readHandlers = new Map();

// ── Server Setup ───────────────────────────────────────────────────────────────
const server = new McpServer({
  name: "pi-ceo",
  version: "3.3.0",
});

// ── Harness staleness check ────────────────────────────────────────────────────
// Returns a warning string if any core harness doc is older than 48 hours.
const HARNESS_STALENESS_THRESHOLD_MS = 48 * 60 * 60 * 1000; // 48 hours
const HARNESS_CORE_DOCS = [
  "executive-summary.md",
  "feature_list.json",
  "sprint_plan.md",
  "handoff.md",
];

function harnessStalenessBanner() {
  const now = Date.now();
  const stale = [];
  for (const doc of HARNESS_CORE_DOCS) {
    const p = path.join(HARNESS_DIR, doc);
    try {
      const stat = fs.statSync(p);
      const ageMs = now - stat.mtimeMs;
      if (ageMs > HARNESS_STALENESS_THRESHOLD_MS) {
        const ageH = Math.round(ageMs / 3600000);
        stale.push(`  - ${doc} (last updated ${ageH}h ago)`);
      }
    } catch (_) {
      stale.push(`  - ${doc} (missing)`);
    }
  }
  if (!stale.length) return "";
  return (
    "\n\n---\n" +
    "⚠️  **HARNESS DOCS STALE (>48h)** — regenerate before trusting this data.\n" +
    "Stale files:\n" +
    stale.join("\n") +
    "\n\nRun `mcp__pi-ceo__get_last_analysis` after a full board meeting or sprint close to refresh."
  );
}

// ── Tool: get_last_analysis ────────────────────────────────────────────────────
const _handle_get_last_analysis = async () => {
  const spec = readHarness("spec.md");
  const exec = readHarness("executive-summary.md");
  const stale = harnessStalenessBanner();
  return { content: [{ type: "text", text: `${spec}\n\n---\n\n${exec}${stale}` }] };
};
_readHandlers.set("get_last_analysis", _handle_get_last_analysis);
server.registerTool(
  "get_last_analysis",
  {
    title: "Get Last Pi CEO Analysis",
    description: "Get the full Pi CEO analysis from the last run (spec + executive summary). Use this to answer questions about any recently analysed repository.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_last_analysis
);

// ── Tool: generate_board_notes ─────────────────────────────────────────────────
server.registerTool(
  "generate_board_notes",
  {
    title: "Generate Board Meeting Notes",
    description: "Generate formatted board meeting notes from the last Pi CEO analysis. Returns a structured document ready to share with stakeholders.",
    inputSchema: {
      meeting_date: z.string().optional().describe("ISO date e.g. 2026-04-07. Defaults to today."),
      attendees: z.string().optional().describe("Comma-separated list of attendees."),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async ({ meeting_date, attendees }) => {
    const exec = readHarness("executive-summary.md");
    const spec = readHarness("spec.md");
    const date = meeting_date || new Date().toISOString().slice(0, 10);
    const people = attendees ? `\nAttendees: ${attendees}` : "";

    const notes = `# Board Meeting Notes — Pi CEO Analysis Review\nDate: ${date}${people}\n\n---\n\n${exec}\n\n---\n\n## Full Technical Specification\n\n${spec}\n\n---\n\n*Generated by Pi CEO Autonomous Dev Platform*\n*Powered by Claude + TAO Framework*`;

    // RA-926: auto-write to Obsidian vault if token is configured
    let obsidianStatus = "";
    if (OBSIDIAN_TOKEN) {
      const vaultPath = `Pi-CEO/${date}-board-notes.md`;
      try {
        await obsidianWrite(vaultPath, notes);
        obsidianStatus = `\n\n✅ **Obsidian:** Note written to \`${vaultPath}\``;
      } catch (e) {
        obsidianStatus = `\n\n⚠️ **Obsidian write failed:** ${e.message}`;
      }
    }

    return { content: [{ type: "text", text: notes + obsidianStatus }] };
  }
);

// ── Tool: write_obsidian_note ──────────────────────────────────────────────────
server.registerTool(
  "write_obsidian_note",
  {
    title: "Write Obsidian Note",
    description: "Write (create or overwrite) a Markdown note in the local Obsidian vault via the Local REST API plugin. The vault must be open in Obsidian and the Local REST API plugin must be enabled. Set OBSIDIAN_TOKEN in the MCP env block.",
    inputSchema: {
      path: z.string().describe("Vault-relative path, e.g. 'Pi-CEO/2026-04-14-sprint-11.md'. Parent folders are created automatically by Obsidian."),
      content: z.string().describe("Full Markdown content to write. Creates the note if it doesn't exist; overwrites if it does."),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
  },
  async ({ path: vaultPath, content }) => {
    try {
      await obsidianWrite(vaultPath, content);
      return {
        content: [{
          type: "text",
          text: `✅ Note written to Obsidian vault at \`${vaultPath}\`\n(${content.length} characters)`,
        }],
      };
    } catch (e) {
      return {
        content: [{ type: "text", text: `❌ Obsidian write failed: ${e.message}` }],
        isError: true,
      };
    }
  }
);

// ── Tool: search_lessons ──────────────────────────────────────────────────────
const _handle_search_lessons = async ({ query, n = 5, category }) => {
  const lessonsPath = path.join(HARNESS_DIR, "lessons.jsonl");
  if (!fs.existsSync(lessonsPath)) {
    return { content: [{ type: "text", text: "No lessons.jsonl found. Lessons are added automatically during analysis runs." }] };
  }

  // Parse JSONL
  const lines = fs.readFileSync(lessonsPath, "utf8").split("\n").filter(Boolean);
  let lessons = lines.map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);

  if (category) {
    lessons = lessons.filter((e) => (e.category || "").toLowerCase() === category.toLowerCase());
  }

  if (!lessons.length) {
    return { content: [{ type: "text", text: `No lessons found${category ? ` in category '${category}'` : ""}.` }] };
  }

  // Simple BM25-style keyword scoring
  const queryTerms = query.toLowerCase().match(/[a-z0-9]+/g) || [];
  if (!queryTerms.length) {
    // No terms — return newest entries
    const recent = lessons.slice(-n).reverse();
    const lines2 = recent.map((e, i) =>
      `${i + 1}. [${e.severity === "warn" ? "⚠️ " : "  "}${e.category}] ${e.lesson}`
    ).join("\n\n");
    return { content: [{ type: "text", text: `${recent.length} most recent lessons:\n\n${lines2}` }] };
  }

  const N = lessons.length;
  const df = {};
  for (const term of queryTerms) {
    df[term] = lessons.filter((e) => (e.lesson || "").toLowerCase().includes(term)).length;
  }

  const scored = lessons.map((e) => {
    const text = (e.lesson || "").toLowerCase();
    const tokens = text.match(/[a-z0-9]+/g) || [];
    const tf = {};
    for (const t of tokens) { tf[t] = (tf[t] || 0) + 1; }
    let score = 0;
    for (const term of queryTerms) {
      const termTf = (tf[term] || 0) / (tokens.length || 1);
      const idf = Math.log((N + 1) / ((df[term] || 0) + 1));
      score += termTf * idf;
    }
    if (e.severity === "warn") score *= 1.2;
    return { ...e, _score: score };
  });

  const top = scored
    .filter((e) => e._score > 0)
    .sort((a, b) => b._score - a._score)
    .slice(0, n);

  if (!top.length) {
    return { content: [{ type: "text", text: `No lessons matched "${query}". Try broader terms.` }] };
  }

  const resultLines = top.map((e, i) =>
    `${i + 1}. [score=${e._score.toFixed(3)}] ${e.severity === "warn" ? "⚠️ " : ""}${e.lesson}\n   category=${e.category} | source=${e.source}`
  ).join("\n\n");

  return {
    content: [{
      type: "text",
      text: `Found ${top.length} lesson(s) for "${query}":\n\n${resultLines}\n\n---\nFor semantic search: \`python .harness/lessons_search.py "${query}"\``,
    }],
  };
};
_readHandlers.set("search_lessons", _handle_search_lessons);
server.registerTool(
  "search_lessons",
  {
    title: "Search Lessons",
    description: "Search the Pi CEO institutional memory (lessons.jsonl) for lessons relevant to a topic. Uses keyword scoring — for semantic search run .harness/lessons_search.py locally.",
    inputSchema: {
      query: z.string().describe("Topic or question to search for, e.g. 'Railway deployment restart' or 'session persistence'"),
      n: z.number().optional().describe("Max results to return (default 5)"),
      category: z.string().optional().describe("Filter by category, e.g. 'persistence', 'security', 'devops'"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_search_lessons
);

// ── Tool: get_sprint_plan ──────────────────────────────────────────────────────
const _handle_get_sprint_plan = async () => {
  // Prefer dedicated sprint_plan.md; fall back to parsing spec.md
  const sprintPath = path.join(HARNESS_DIR, "sprint_plan.md");
  if (fs.existsSync(sprintPath)) {
    return { content: [{ type: "text", text: fs.readFileSync(sprintPath, "utf8") }] };
  }
  const spec = readHarness("spec.md");
  const match = spec.match(/## Sprint Plan([\s\S]*?)(?:\n##|$)/);
  const sprint = match ? match[1].trim() : spec;
  return { content: [{ type: "text", text: sprint }] };
};
_readHandlers.set("get_sprint_plan", _handle_get_sprint_plan);
server.registerTool(
  "get_sprint_plan",
  {
    title: "Get Sprint Plan",
    description: "Get the prioritised sprint plan from the last Pi CEO analysis with full task details.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_sprint_plan
);

// ── Tool: get_feature_list ─────────────────────────────────────────────────────
const _handle_get_feature_list = async () => {
  const features = readHarness("feature_list.json");
  return { content: [{ type: "text", text: features }] };
};
_readHandlers.set("get_feature_list", _handle_get_feature_list);
server.registerTool(
  "get_feature_list",
  {
    title: "Get Feature List",
    description: "Get the full feature list JSON from the last Pi CEO analysis.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_feature_list
);

// ── Tool: list_harness_files ───────────────────────────────────────────────────
const _handle_list_harness_files = async () => {
  if (!fs.existsSync(HARNESS_DIR)) {
    return { content: [{ type: "text", text: "No .harness/ directory found. Run an analysis first at https://dashboard-unite-group.vercel.app/dashboard" }] };
  }
  const files = fs.readdirSync(HARNESS_DIR)
    .map((f) => {
      const stat = fs.statSync(path.join(HARNESS_DIR, f));
      return `${f} (${Math.round(stat.size / 1024)}KB, ${stat.mtime.toISOString().slice(0, 10)})`;
    })
    .join("\n");
  return { content: [{ type: "text", text: `Harness files in ${HARNESS_DIR}:\n\n${files}` }] };
};
_readHandlers.set("list_harness_files", _handle_list_harness_files);
server.registerTool(
  "list_harness_files",
  {
    title: "List Harness Files",
    description: "List all files in the .harness/ directory from the last Pi CEO analysis run.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_list_harness_files
);

// ── Tool: get_zte_score ────────────────────────────────────────────────────────
const _handle_get_zte_score = async () => {
  // Read leverage-audit.md directly — authoritative source, updated each sprint
  const auditPath = path.join(HARNESS_DIR, "leverage-audit.md");
  if (fs.existsSync(auditPath)) {
    return { content: [{ type: "text", text: fs.readFileSync(auditPath, "utf8") }] };
  }
  // Fallback: parse spec.md for legacy data
  const spec = readHarness("spec.md");
  const match = spec.match(/## ZTE Maturity([\s\S]*?)(?:\n##|$)/);
  const match2 = spec.match(/## (?:\d+\.\s*)?(?:Current )?Leverage Audit([\s\S]*?)(?:\n##|$)/);
  const zte = match ? match[1].trim() : "";
  const leverage = match2 ? match2[1].trim() : "";
  const text = zte || leverage || "No ZTE data found. Run an analysis first.";
  return { content: [{ type: "text", text: `## ZTE Maturity\n\n${text}` }] };
};
_readHandlers.set("get_zte_score", _handle_get_zte_score);
server.registerTool(
  "get_zte_score",
  {
    title: "Get ZTE Maturity Score",
    description: "Get the Zero Touch Execution maturity score and leverage point breakdown from the last analysis.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_zte_score
);

// ── Tool: linear_list_issues ───────────────────────────────────────────────────
const _handle_linear_list_issues = async ({ status, limit }) => {
  const project = await findProjectId();

  let statusFilter = "";
  if (status) {
    const statusMap = {
      backlog: "Backlog", todo: "Todo", in_progress: "In Progress",
      done: "Done", canceled: "Canceled", cancelled: "Canceled",
    };
    const mapped = statusMap[status.toLowerCase()] || status;
    statusFilter = `, state: { name: { eq: "${mapped}" } }`;
  }

  const data = await linearGql(`{
    issues(
      filter: { project: { id: { eq: "${project.id}" } }${statusFilter} }
      first: ${limit}
      orderBy: updatedAt
    ) {
      nodes {
        id identifier title
        state { name type }
        priority priorityLabel
        assignee { name }
        labels { nodes { name } }
        estimate
        dueDate
        createdAt updatedAt
        description
      }
    }
  }`);

  const issues = data.issues.nodes;
  if (!issues.length) {
    return { content: [{ type: "text", text: `No issues found in project "${project.name}"${status ? ` with status "${status}"` : ""}.` }] };
  }

  const lines = [`# ${project.name} — ${issues.length} Issues${status ? ` (${status})` : ""}`, ""];
  for (const issue of issues) {
    const labels = issue.labels?.nodes?.map(l => l.name).join(", ") || "";
    lines.push(`## ${issue.identifier}: ${issue.title}`);
    lines.push(`- **Status**: ${issue.state?.name || "Unknown"} | **Priority**: ${issue.priorityLabel || "None"}`);
    if (issue.assignee) lines.push(`- **Assignee**: ${issue.assignee.name}`);
    if (labels) lines.push(`- **Labels**: ${labels}`);
    if (issue.estimate) lines.push(`- **Estimate**: ${issue.estimate}`);
    if (issue.dueDate) lines.push(`- **Due**: ${issue.dueDate}`);
    lines.push("");
  }

  return { content: [{ type: "text", text: lines.join("\n") }] };
};
_readHandlers.set("linear_list_issues", _handle_linear_list_issues);
server.registerTool(
  "linear_list_issues",
  {
    title: "List Linear Issues",
    description: "List issues from the Pi-Dev-Ops Linear project. Filter by status (backlog, todo, in_progress, done, canceled) or get all. Returns title, status, priority, assignee, and labels.",
    inputSchema: {
      status: z.string().optional().describe("Filter by status: backlog, todo, in_progress, done, canceled. Leave empty for all."),
      limit: z.number().int().min(1).max(100).default(50).describe("Maximum issues to return (default 50)"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_linear_list_issues
);

// ── Tool: linear_create_issue ──────────────────────────────────────────────────
server.registerTool(
  "linear_create_issue",
  {
    title: "Create Linear Issue",
    description: "Create a new issue in a Linear project. Use project_key (e.g. 'restoreassist', 'carsi', 'synthex', 'dr-nrpg') to route to the correct repo's project — reads .harness/projects.json. Omit project_key to default to Pi-Dev-Ops.",
    inputSchema: {
      title: z.string().min(1).describe("Issue title"),
      description: z.string().optional().describe("Issue description in Markdown"),
      priority: z.number().int().min(0).max(4).default(3).describe("Priority: 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low"),
      labels: z.array(z.string()).optional().describe("Array of label names to apply"),
      status: z.string().optional().describe("Initial status: backlog, todo, in_progress. Defaults to backlog."),
      project_key: z.string().optional().describe("Repo key from .harness/projects.json (e.g. 'restoreassist', 'carsi', 'synthex', 'dr-nrpg', 'unite-group', 'ccw-crm'). Omit to default to Pi-Dev-Ops."),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ title, description, priority, labels, status, project_key }) => {
    // RA-1518 gap #4: route to target repo's project when project_key given
    const routed = resolveProjectRouting(project_key);
    const team = routed ? { id: routed.teamId, key: routed.teamKey } : await findTeamId();
    const project = routed ? { id: routed.projectId } : await findProjectId();

    // Build state filter if status specified
    let stateId = null;
    if (status) {
      const statusMap = { backlog: "Backlog", todo: "Todo", in_progress: "In Progress" };
      const mapped = statusMap[status.toLowerCase()] || status;
      const stateData = await linearGql(`{
        workflowStates(filter: { team: { id: { eq: "${team.id}" } }, name: { eq: "${mapped}" } }) {
          nodes { id name }
        }
      }`);
      if (stateData.workflowStates.nodes.length > 0) {
        stateId = stateData.workflowStates.nodes[0].id;
      }
    }

    // Find label IDs if specified
    let labelIds = [];
    if (labels && labels.length > 0) {
      const labelData = await linearGql(`{
        issueLabels { nodes { id name } }
      }`);
      const allLabels = labelData.issueLabels.nodes;
      for (const labelName of labels) {
        const found = allLabels.find(l => l.name.toLowerCase() === labelName.toLowerCase());
        if (found) labelIds.push(found.id);
      }
    }

    const input = {
      title,
      teamId: team.id,
      projectId: project.id,
      priority,
    };
    if (description) input.description = description;
    if (stateId) input.stateId = stateId;
    if (labelIds.length > 0) input.labelIds = labelIds;

    const data = await linearGql(`
      mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
          success
          issue { id identifier title url state { name } priorityLabel }
        }
      }
    `, { input });

    const issue = data.issueCreate.issue;
    return {
      content: [{
        type: "text",
        text: `Issue created successfully!\n\n**${issue.identifier}**: ${issue.title}\n- Status: ${issue.state.name}\n- Priority: ${issue.priorityLabel}\n- URL: ${issue.url}`,
      }],
    };
  }
);

// ── Tool: linear_update_issue ──────────────────────────────────────────────────
server.registerTool(
  "linear_update_issue",
  {
    title: "Update Linear Issue",
    description: "Update an existing Linear issue. Use the identifier (e.g. UNI-123) or issue ID. Can update status, priority, title, description, and assignee.",
    inputSchema: {
      identifier: z.string().min(1).describe("Issue identifier (e.g. UNI-123) or issue ID"),
      title: z.string().optional().describe("New title"),
      description: z.string().optional().describe("New description (Markdown)"),
      status: z.string().optional().describe("New status: backlog, todo, in_progress, done, canceled"),
      priority: z.number().int().min(0).max(4).optional().describe("New priority: 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
  },
  async ({ identifier, title, description, status, priority }) => {
    // Find the issue by identifier
    const searchData = await linearGql(`{
      issues(filter: { or: [
        { id: { eq: "${identifier}" } },
        { number: { eq: ${parseInt(identifier.replace(/\D/g, "")) || 0} } }
      ] }) {
        nodes { id identifier team { id } }
      }
    }`);

    let issue = searchData.issues.nodes[0];
    if (!issue) {
      // Try searching by identifier prefix
      const searchData2 = await linearGql(`{
        searchIssues(term: "${identifier}", first: 1) {
          nodes { id identifier team { id } }
        }
      }`);
      issue = searchData2.searchIssues?.nodes?.[0];
    }
    if (!issue) throw new Error(`Issue "${identifier}" not found`);

    const input = {};
    if (title) input.title = title;
    if (description) input.description = description;
    if (priority !== undefined) input.priority = priority;

    if (status) {
      const statusMap = {
        backlog: "Backlog", todo: "Todo", in_progress: "In Progress",
        done: "Done", canceled: "Canceled", cancelled: "Canceled",
      };
      const mapped = statusMap[status.toLowerCase()] || status;
      const stateData = await linearGql(`{
        workflowStates(filter: { team: { id: { eq: "${issue.team.id}" } }, name: { eq: "${mapped}" } }) {
          nodes { id name }
        }
      }`);
      if (stateData.workflowStates.nodes.length > 0) {
        input.stateId = stateData.workflowStates.nodes[0].id;
      }
    }

    const data = await linearGql(`
      mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
          success
          issue { id identifier title url state { name } priorityLabel }
        }
      }
    `, { id: issue.id, input });

    const updated = data.issueUpdate.issue;
    return {
      content: [{
        type: "text",
        text: `Issue updated!\n\n**${updated.identifier}**: ${updated.title}\n- Status: ${updated.state.name}\n- Priority: ${updated.priorityLabel}\n- URL: ${updated.url}`,
      }],
    };
  }
);

// ── Tool: linear_search_issues ─────────────────────────────────────────────────
const _handle_linear_search_issues = async ({ query, limit }) => {
  const project = await findProjectId();

  const data = await linearGql(`{
    searchIssues(term: "${query.replace(/"/g, '\\"')}", first: ${limit}) {
      nodes {
        id identifier title
        state { name }
        priorityLabel
        assignee { name }
        project { id name }
        url
      }
    }
  }`);

  // Filter to our project
  const issues = data.searchIssues.nodes.filter(
    i => i.project?.id === project.id
  );

  if (!issues.length) {
    return { content: [{ type: "text", text: `No issues found matching "${query}" in ${project.name}.` }] };
  }

  const lines = [`# Search: "${query}" — ${issues.length} results`, ""];
  for (const issue of issues) {
    lines.push(`- **${issue.identifier}**: ${issue.title} [${issue.state?.name}] (${issue.priorityLabel || "No priority"}) ${issue.url}`);
  }

  return { content: [{ type: "text", text: lines.join("\n") }] };
};
_readHandlers.set("linear_search_issues", _handle_linear_search_issues);
server.registerTool(
  "linear_search_issues",
  {
    title: "Search Linear Issues",
    description: "Search issues in the Pi-Dev-Ops Linear project by text query. Searches across titles and descriptions.",
    inputSchema: {
      query: z.string().min(1).describe("Search text to find in issue titles and descriptions"),
      limit: z.number().int().min(1).max(50).default(20).describe("Max results (default 20)"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_linear_search_issues
);

// ── Tool: linear_sync_board ────────────────────────────────────────────────────
server.registerTool(
  "linear_sync_board",
  {
    title: "Sync Linear Board",
    description: "Get a full board view of all Pi-Dev-Ops issues grouped by status. Shows Backlog, Todo, In Progress, Done columns like a kanban board.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
    const project = await findProjectId();

    const data = await linearGql(`{
      issues(
        filter: { project: { id: { eq: "${project.id}" } } }
        first: 250
        orderBy: updatedAt
      ) {
        nodes {
          identifier title
          state { name type }
          priorityLabel
          assignee { name }
          labels { nodes { name } }
          estimate
        }
      }
    }`);

    const issues = data.issues.nodes;
    const groups = {};
    const order = ["Backlog", "Triage", "Todo", "In Progress", "In Review", "Done", "Canceled"];

    for (const issue of issues) {
      const status = issue.state?.name || "Unknown";
      if (!groups[status]) groups[status] = [];
      groups[status].push(issue);
    }

    const lines = [
      `# ${project.name} — Board View`,
      `_${issues.length} total issues_`,
      "",
    ];

    // Ordered columns first, then any extras
    const allStatuses = [...new Set([...order.filter(s => groups[s]), ...Object.keys(groups)])];

    for (const status of allStatuses) {
      const items = groups[status];
      if (!items) continue;
      lines.push(`## ${status} (${items.length})`);
      for (const issue of items) {
        const labels = issue.labels?.nodes?.map(l => l.name).join(", ");
        const assignee = issue.assignee ? ` @${issue.assignee.name}` : "";
        const labelStr = labels ? ` [${labels}]` : "";
        lines.push(`- **${issue.identifier}**: ${issue.title} (${issue.priorityLabel || "—"})${assignee}${labelStr}`);
      }
      lines.push("");
    }

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// ── Tool: linear_status ───────────────────────────────────────────────────────
const _handle_linear_status = async () => {
  if (!LINEAR_API_KEY) {
    return {
      content: [{
        type: "text",
        text: [
          "## Linear Auth Status: NOT CONFIGURED",
          "",
          "LINEAR_API_KEY is not set. The pi-ceo linear_* tools cannot reach Linear.",
          "",
          "### How to fix",
          "",
          "1. Get a Linear API key from: https://linear.app/settings/api",
          "2. Add it to your Claude Desktop config at:",
          "   `%APPDATA%\\Claude\\claude_desktop_config.json`",
          "",
          "```json",
          "{",
          '  "mcpServers": {',
          '    "pi-ceo": {',
          '      "command": "node",',
          `      "args": ["${path.resolve(__dirname, "pi-ceo-server.js")}"],`,
          '      "env": {',
          '        "LINEAR_API_KEY": "lin_api_YOUR_KEY_HERE"',
          "      }",
          "    }",
          "  }",
          "}",
          "```",
          "",
          "3. Restart Claude Desktop (the MCP server is cached as a subprocess)",
          "4. Run `linear_status` again to confirm it's working",
        ].join("\n"),
      }],
    };
  }

  // Test the key with a minimal query
  try {
    const data = await linearGql(`{ viewer { id name email } }`);
    const user = data.viewer;
    return {
      content: [{
        type: "text",
        text: [
          "## Linear Auth Status: CONNECTED",
          "",
          `Authenticated as: **${user.name}** (${user.email})`,
          `User ID: ${user.id}`,
          "",
          "All linear_* tools are operational.",
        ].join("\n"),
      }],
    };
  } catch (e) {
    return {
      content: [{
        type: "text",
        text: [
          "## Linear Auth Status: AUTH FAILED",
          "",
          `Error: ${e.message}`,
          "",
          "LINEAR_API_KEY is set but the API rejected it.",
          "Check that the key is valid and has not been revoked.",
          "Get a new key at: https://linear.app/settings/api",
        ].join("\n"),
      }],
    };
  }
};
_readHandlers.set("linear_status", _handle_linear_status);
server.registerTool(
  "linear_status",
  {
    title: "Linear Auth Status",
    description: "Check if the Linear API key is configured and verify it can reach the Linear API. Use this to diagnose auth issues before running other linear_* tools.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_linear_status
);

// ── Tool: get_project_health ──────────────────────────────────────────────────
const _handle_get_project_health = async ({ project_id }) => {
  const resultsDir = path.join(HARNESS_DIR, "scan-results");
  const projectsFile = path.join(HARNESS_DIR, "projects.json");

  let projects;
  try {
    projects = JSON.parse(fs.readFileSync(projectsFile, "utf8")).projects;
  } catch {
    return { content: [{ type: "text", text: "projects.json not found — run a scan first." }] };
  }

  if (project_id) {
    projects = projects.filter(p => p.id === project_id);
    if (!projects.length) {
      return { content: [{ type: "text", text: `Project '${project_id}' not found in projects.json` }] };
    }
  }

  const scanTypes = ["security", "code_quality", "dependencies", "deployment_health"];
  const lines = ["# Pi-SEO Project Health", ""];

  for (const proj of projects) {
    const projDir = path.join(resultsDir, proj.id);
    const scores = {};
    const counts = {};

    if (fs.existsSync(projDir)) {
      for (const st of scanTypes) {
        const files = fs.readdirSync(projDir).filter(f => f.endsWith(`-${st}.json`)).sort();
        if (!files.length) continue;
        try {
          const data = JSON.parse(fs.readFileSync(path.join(projDir, files[files.length - 1]), "utf8"));
          scores[st] = data.health_score ?? 100;
          counts[st] = (data.findings ?? []).length;
        } catch { /* skip corrupt file */ }
      }
    }

    const scoreValues = Object.values(scores);
    const overall = scoreValues.length
      ? Math.round(scoreValues.reduce((a, b) => a + b, 0) / scoreValues.length)
      : null;

    const indicator = overall === null ? "⬜" : overall >= 80 ? "🟢" : overall >= 60 ? "🟡" : "🔴";
    lines.push(`## ${indicator} ${proj.id} — ${proj.repo}`);
    lines.push(`**Overall health:** ${overall !== null ? overall + "/100" : "not scanned yet"}`);

    if (Object.keys(scores).length) {
      lines.push("");
      lines.push("| Scan Type | Score | Findings |");
      lines.push("|-----------|-------|----------|");
      for (const st of scanTypes) {
        if (scores[st] !== undefined) {
          lines.push(`| ${st} | ${scores[st]}/100 | ${counts[st] ?? 0} |`);
        }
      }
    }

    if (proj.deployments && Object.keys(proj.deployments).length) {
      lines.push("");
      lines.push("**Deployments:** " + Object.entries(proj.deployments).map(([k, v]) => `${k}: ${v}`).join(" · "));
    }
    lines.push("");
  }

  return { content: [{ type: "text", text: lines.join("\n") }] };
};
_readHandlers.set("get_project_health", _handle_get_project_health);
server.registerTool(
  "get_project_health",
  {
    title: "Get Project Health",
    description: "Get the latest Pi-SEO scan results and health scores for one or all registered projects. Returns overall health score (0-100), per-scan-type scores, and finding counts.",
    inputSchema: {
      project_id: z.string().optional().describe("Project ID (e.g. 'pi-dev-ops'). Omit to get all projects."),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_project_health
);

// ── Tool: scan_project ────────────────────────────────────────────────────────
server.registerTool(
  "scan_project",
  {
    title: "Scan Project",
    description: "Trigger a Pi-SEO autonomous scan for one or all projects via the Pi-CEO API. Runs async — call get_project_health after a few minutes to see results.",
    inputSchema: {
      project_id: z.string().optional().describe("Project ID to scan. Omit to scan all projects."),
      scan_types: z.array(z.enum(["security", "code_quality", "dependencies", "deployment_health"])).optional().describe("Scan types to run. Omit for all."),
      dry_run: z.boolean().optional().describe("Simulate ticket creation without hitting Linear (default: false)."),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ project_id, scan_types, dry_run }) => {
    const PI_CEO_URL = process.env.PI_CEO_URL || "http://127.0.0.1:7777";
    const PI_CEO_PASSWORD = process.env.PI_CEO_PASSWORD || "";
    const http = require(PI_CEO_URL.startsWith("https") ? "https" : "http");

    function httpPost(url, body, headers = {}) {
      return new Promise((resolve, reject) => {
        const u = new URL(url);
        const data = JSON.stringify(body);
        const req = http.request(u, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data), ...headers },
        }, (res) => {
          let out = "";
          res.on("data", c => out += c);
          res.on("end", () => resolve({ status: res.statusCode, body: out, headers: res.headers }));
        });
        req.on("error", reject);
        req.write(data);
        req.end();
      });
    }

    // Login to get session cookie
    let sessionCookie;
    try {
      const loginRes = await httpPost(`${PI_CEO_URL}/api/login`, { password: PI_CEO_PASSWORD });
      if (loginRes.status !== 200) throw new Error(`HTTP ${loginRes.status}`);
      const cookie = (loginRes.headers["set-cookie"] || []).find(c => c.startsWith("tao_session="));
      if (!cookie) throw new Error("No session cookie in response");
      sessionCookie = cookie.split(";")[0];
    } catch (e) {
      return { content: [{ type: "text", text: `Login to Pi-CEO failed: ${e.message}\n\nEnsure PI_CEO_URL and PI_CEO_PASSWORD are set in MCP env config.` }] };
    }

    // Trigger scan
    try {
      await httpPost(`${PI_CEO_URL}/api/scan`, { project_id, scan_types, dry_run: dry_run ?? false }, { "Cookie": sessionCookie });
    } catch (e) {
      return { content: [{ type: "text", text: `Scan trigger failed: ${e.message}` }] };
    }

    const scope = project_id ? `project '${project_id}'` : "all projects";
    const types = scan_types ? scan_types.join(", ") : "all scan types";
    return {
      content: [{
        type: "text",
        text: [
          `✅ Scan triggered for ${scope} (${types})${dry_run ? " — DRY RUN" : ""}.`,
          "",
          "Results are saved to `.harness/scan-results/` as they complete.",
          "Call `get_project_health` in a few minutes to see updated scores.",
          dry_run ? "\n> DRY RUN: no Linear tickets will be created." : "",
        ].join("\n"),
      }],
    };
  }
);

// ── Tool: get_monitor_digest ──────────────────────────────────────────────────
const _handle_get_monitor_digest = async () => {
  const digestsDir = path.join(HARNESS_DIR, "monitor-digests");
  if (!fs.existsSync(digestsDir)) {
    return { content: [{ type: "text", text: "No monitor digests found. Run `run_monitor_cycle` first." }] };
  }
  const files = fs.readdirSync(digestsDir).filter(f => f.endsWith(".json")).sort().reverse();
  if (!files.length) {
    return { content: [{ type: "text", text: "No monitor digests found. Run `run_monitor_cycle` first." }] };
  }
  try {
    const digest = JSON.parse(fs.readFileSync(path.join(digestsDir, files[0]), "utf8"));
    const md = digest.digest_markdown || JSON.stringify(digest, null, 2);
    return { content: [{ type: "text", text: md }] };
  } catch (e) {
    return { content: [{ type: "text", text: `Failed to read digest: ${e.message}` }] };
  }
};
_readHandlers.set("get_monitor_digest", _handle_get_monitor_digest);
server.registerTool(
  "get_monitor_digest",
  {
    title: "Get Monitor Digest",
    description: "Return the latest Pi-SEO portfolio health monitor digest. Shows portfolio health score, per-project deltas, regressions, systemic issues, and alerts.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_monitor_digest
);

// ── Tool: run_monitor_cycle ───────────────────────────────────────────────────
server.registerTool(
  "run_monitor_cycle",
  {
    title: "Run Monitor Cycle",
    description: "Trigger a Pi-SEO portfolio health monitor cycle via the Pi-CEO API. Detects regressions, systemic issues, and routes critical alerts to Linear. Runs async — call get_monitor_digest after a minute to see results.",
    inputSchema: {
      project_id: z.string().optional().describe("Scope to a single project ID. Omit for all projects."),
      use_agent: z.boolean().optional().describe("Enable AI remediation analysis (requires ANTHROPIC_API_KEY on server, default: false)."),
      dry_run: z.boolean().optional().describe("Skip ticket creation and digest save (default: false)."),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ project_id, use_agent, dry_run }) => {
    const PI_CEO_URL = process.env.PI_CEO_URL || "http://127.0.0.1:7777";
    const PI_CEO_PASSWORD = process.env.PI_CEO_PASSWORD || "";
    const http = require(PI_CEO_URL.startsWith("https") ? "https" : "http");

    function httpPost(url, body, headers = {}) {
      return new Promise((resolve, reject) => {
        const u = new URL(url);
        const data = JSON.stringify(body);
        const req = http.request(u, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data), ...headers },
        }, (res) => {
          let out = "";
          res.on("data", c => out += c);
          res.on("end", () => resolve({ status: res.statusCode, body: out, headers: res.headers }));
        });
        req.on("error", reject);
        req.write(data);
        req.end();
      });
    }

    // Login to get session cookie
    let sessionCookie;
    try {
      const loginRes = await httpPost(`${PI_CEO_URL}/api/login`, { password: PI_CEO_PASSWORD });
      if (loginRes.status !== 200) throw new Error(`HTTP ${loginRes.status}`);
      const cookie = (loginRes.headers["set-cookie"] || []).find(c => c.startsWith("tao_session="));
      if (!cookie) throw new Error("No session cookie in response");
      sessionCookie = cookie.split(";")[0];
    } catch (e) {
      return { content: [{ type: "text", text: `Login to Pi-CEO failed: ${e.message}\n\nEnsure PI_CEO_URL and PI_CEO_PASSWORD are set in MCP env config.` }] };
    }

    // Trigger monitor cycle
    try {
      await httpPost(
        `${PI_CEO_URL}/api/monitor`,
        { project_id: project_id ?? null, use_agent: use_agent ?? false, dry_run: dry_run ?? false },
        { "Cookie": sessionCookie }
      );
    } catch (e) {
      return { content: [{ type: "text", text: `Monitor trigger failed: ${e.message}` }] };
    }

    const scope = project_id ? `project '${project_id}'` : "all projects";
    return {
      content: [{
        type: "text",
        text: [
          `✅ Monitor cycle triggered for ${scope}${dry_run ? " — DRY RUN" : ""}.`,
          "",
          "The monitor agent is analysing scan results in the background.",
          "Call `get_monitor_digest` in about a minute to see the portfolio health report.",
          dry_run ? "\n> DRY RUN: no Linear tickets will be created and no digest will be saved." : "",
        ].join("\n"),
      }],
    };
  }
);

// ── Ship Chain tools (shared HTTP helper) ─────────────────────────────────────

function _shipHttp(method, url, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const http = require(url.startsWith("https") ? "https" : "http");
    const u = new URL(url);
    const data = body ? JSON.stringify(body) : null;
    const opts = {
      method,
      headers: {
        ...(data ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } : {}),
        ...headers,
      },
    };
    const req = http.request(u, opts, (res) => {
      let out = "";
      res.on("data", c => out += c);
      res.on("end", () => resolve({ status: res.statusCode, body: out, headers: res.headers }));
    });
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}

async function _shipLogin() {
  const PI_CEO_URL = process.env.PI_CEO_URL || "http://127.0.0.1:7777";
  const PI_CEO_PASSWORD = process.env.PI_CEO_PASSWORD || "";
  const res = await _shipHttp("POST", `${PI_CEO_URL}/api/login`, { password: PI_CEO_PASSWORD });
  if (res.status !== 200) throw new Error(`Login failed HTTP ${res.status}`);
  const cookie = (res.headers["set-cookie"] || []).find(c => c.startsWith("tao_session="));
  if (!cookie) throw new Error("No session cookie");
  return { cookie: cookie.split(";")[0], url: PI_CEO_URL };
}

// ── Tool: spec_idea ───────────────────────────────────────────────────────────
server.registerTool(
  "spec_idea",
  {
    title: "Spec Idea",
    description: "Phase 1 of the Ship Chain. Converts a raw idea into a structured spec.md with PITER classification, goals, acceptance criteria, and constraints. Auto-generates a .harness/config.yaml for new projects (RA-691). Returns a pipeline_id to track all subsequent phases.",
    inputSchema: {
      idea: z.string().describe("The raw idea or requirement to specify (e.g. 'add dark mode toggle to settings')"),
      repo_url: z.string().describe("GitHub repo URL this change targets"),
      pipeline_id: z.string().optional().describe("Optional pipeline ID (e.g. RA-547). Auto-generated if omitted."),
      model: z.enum(["sonnet", "opus", "haiku"]).optional().describe("Claude model (default: sonnet)"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ idea, repo_url, pipeline_id, model }) => {
    try {
      const { cookie, url } = await _shipLogin();
      const body = { idea, repo_url, pipeline_id: pipeline_id ?? null, model: model ?? "sonnet" };
      const res = await _shipHttp("POST", `${url}/api/spec`, body, { Cookie: cookie });
      const data = JSON.parse(res.body);
      return {
        content: [{
          type: "text",
          text: [
            `✅ Spec phase started. Pipeline ID: **${data.pipeline_id}**`,
            "",
            "The spec agent is writing `spec.md` in the background.",
            `Run \`get_pipeline\` with pipeline_id="${data.pipeline_id}" to check progress.`,
            "When current_phase is 'plan', run \`plan_build\` to generate the implementation plan.",
          ].join("\n"),
        }],
      };
    } catch (e) {
      return { content: [{ type: "text", text: `spec_idea failed: ${e.message}` }] };
    }
  }
);

// ── Tool: plan_build ──────────────────────────────────────────────────────────
server.registerTool(
  "plan_build",
  {
    title: "Plan Build",
    description: "Phase 2 of the Ship Chain. Reads the spec.md and produces a technical implementation plan with files to change, effort sizing, dependencies, and risks.",
    inputSchema: {
      pipeline_id: z.string().describe("Pipeline ID from spec_idea (e.g. RA-547 or abc12345)"),
      model: z.enum(["sonnet", "opus", "haiku"]).optional().describe("Claude model (default: sonnet)"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ pipeline_id, model }) => {
    try {
      const { cookie, url } = await _shipLogin();
      const res = await _shipHttp("POST", `${url}/api/plan`, { pipeline_id, model: model ?? "sonnet" }, { Cookie: cookie });
      const data = JSON.parse(res.body);
      return {
        content: [{
          type: "text",
          text: [
            `✅ Plan phase started for pipeline **${pipeline_id}**.`,
            "",
            "The planner agent is writing `plan.md` in the background.",
            `Run \`get_pipeline\` with pipeline_id="${pipeline_id}" to check progress.`,
            "When current_phase is 'build', run \`build_feature\` to start the implementation.",
          ].join("\n"),
        }],
      };
    } catch (e) {
      return { content: [{ type: "text", text: `plan_build failed: ${e.message}` }] };
    }
  }
);

// ── Tool: build_feature ───────────────────────────────────────────────────────
server.registerTool(
  "build_feature",
  {
    title: "Build Feature",
    description: "Phase 3 of the Ship Chain. Starts a build session (clone → analyze → generate → push). Returns a session_id. Provide the pipeline_id to link the session to the pipeline.",
    inputSchema: {
      repo_url: z.string().describe("GitHub repo URL to build"),
      brief: z.string().describe("Implementation brief — paste the plan.md content or summarise the task"),
      pipeline_id: z.string().optional().describe("Pipeline ID to link this build session to"),
      model: z.enum(["sonnet", "opus", "haiku"]).optional().describe("Claude model (default: sonnet)"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ repo_url, brief, pipeline_id, model }) => {
    try {
      const { cookie, url } = await _shipLogin();
      const body = { repo_url, brief: brief ?? "", model: model ?? "sonnet" };
      const res = await _shipHttp("POST", `${url}/api/sessions`, body, { Cookie: cookie });
      const data = JSON.parse(res.body);
      const sessionId = data.id || data.session_id;

      // If pipeline_id given, link session via test endpoint stub (stores session_id)
      if (pipeline_id && sessionId) {
        await _shipHttp("POST", `${url}/api/test`, { pipeline_id, session_id: sessionId }, { Cookie: cookie });
      }

      return {
        content: [{
          type: "text",
          text: [
            `✅ Build session started. Session ID: **${sessionId}**`,
            pipeline_id ? `Pipeline: **${pipeline_id}**` : "",
            "",
            "Monitor progress via the dashboard or WebSocket stream.",
            "When the session completes, run \`test_build\` to verify the implementation.",
          ].filter(Boolean).join("\n"),
        }],
      };
    } catch (e) {
      return { content: [{ type: "text", text: `build_feature failed: ${e.message}` }] };
    }
  }
);

// ── Tool: test_build ──────────────────────────────────────────────────────────
server.registerTool(
  "test_build",
  {
    title: "Test Build",
    description: "Phase 4 of the Ship Chain. Runs the smoke test suite and records results. Must pass before /review is allowed.",
    inputSchema: {
      pipeline_id: z.string().describe("Pipeline ID to record results against"),
      session_id: z.string().describe("Session ID from build_feature"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ pipeline_id, session_id }) => {
    try {
      const { cookie, url } = await _shipLogin();
      await _shipHttp("POST", `${url}/api/test`, { pipeline_id, session_id }, { Cookie: cookie });
      return {
        content: [{
          type: "text",
          text: [
            `✅ Test phase started for pipeline **${pipeline_id}**.`,
            "",
            "Smoke tests are running in the background.",
            `Run \`get_pipeline\` with pipeline_id="${pipeline_id}" to check results.`,
            "When current_phase is 'review', run \`review_build\` for the quality gate.",
          ].join("\n"),
        }],
      };
    } catch (e) {
      return { content: [{ type: "text", text: `test_build failed: ${e.message}` }] };
    }
  }
);

// ── Tool: review_build ────────────────────────────────────────────────────────
server.registerTool(
  "review_build",
  {
    title: "Review Build",
    description: "Phase 5 of the Ship Chain. Runs the evaluator against spec + implementation. Scores on correctness, coverage, quality, security, and documentation. Score ≥ 8/10 required to ship.",
    inputSchema: {
      pipeline_id: z.string().describe("Pipeline ID to review"),
      session_id: z.string().describe("Session ID from build_feature"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ pipeline_id, session_id }) => {
    try {
      const { cookie, url } = await _shipLogin();
      const res = await _shipHttp(
        "POST",
        `${url}/api/sessions/${session_id}/resume`,
        { resume_from: "evaluator", pipeline_id },
        { Cookie: cookie }
      );
      return {
        content: [{
          type: "text",
          text: [
            `✅ Review phase started for pipeline **${pipeline_id}**.`,
            "",
            "The evaluator is scoring the implementation in the background.",
            `Run \`get_pipeline\` with pipeline_id="${pipeline_id}" to see the review score.`,
            "If score ≥ 8/10, run \`ship_build\` to deploy.",
          ].join("\n"),
        }],
      };
    } catch (e) {
      return { content: [{ type: "text", text: `review_build failed: ${e.message}` }] };
    }
  }
);

// ── Tool: ship_build ──────────────────────────────────────────────────────────
server.registerTool(
  "ship_build",
  {
    title: "Ship Build",
    description: "Phase 6 of the Ship Chain. Hard gate: requires all prior phases complete and review score ≥ 8/10. On pass: deploys, writes ship-log.json, updates Linear ticket to Done.",
    inputSchema: {
      pipeline_id: z.string().describe("Pipeline ID to ship (e.g. RA-547 or abc12345)"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ pipeline_id }) => {
    try {
      const { cookie, url } = await _shipLogin();
      const res = await _shipHttp("POST", `${url}/api/ship`, { pipeline_id }, { Cookie: cookie });
      const data = JSON.parse(res.body);
      if (data.ok) {
        const log = data.ship_log || {};
        return {
          content: [{
            type: "text",
            text: [
              `✅ **SHIPPED** — Pipeline ${pipeline_id}`,
              `Review score: ${log.review_score}/10`,
              `Deployed at: ${log.deployed_at}`,
              `Rollback: \`${log.rollback_ref}\``,
              "",
              "Linear ticket updated to Done.",
            ].join("\n"),
          }],
        };
      } else {
        const log = data.ship_log || {};
        return {
          content: [{
            type: "text",
            text: [
              `🚫 **SHIP BLOCKED** — Pipeline ${pipeline_id}`,
              `Blocking gate: ${log.blocking_gate || "unknown"}`,
              `Reason: ${log.blocking_reason || data.error || "Gate check failed"}`,
              "",
              "Fix the blocking issue and re-run the relevant phase before shipping.",
            ].join("\n"),
          }],
        };
      }
    } catch (e) {
      return { content: [{ type: "text", text: `ship_build failed: ${e.message}` }] };
    }
  }
);

// ── Tool: get_pipeline ────────────────────────────────────────────────────────
const _handle_get_pipeline = async ({ pipeline_id }) => {
  try {
    const { cookie, url } = await _shipLogin();
    const res = await _shipHttp("GET", `${url}/api/pipeline/${pipeline_id}`, null, { Cookie: cookie });
    if (res.status === 404) {
      return { content: [{ type: "text", text: `Pipeline '${pipeline_id}' not found.` }] };
    }
    const state = JSON.parse(res.body);
    const phases = ["spec", "plan", "build", "test", "review", "ship"];
    const completed = new Set(state.phases_completed || []);
    const lines = [
      `**Pipeline: ${state.pipeline_id}** — "${(state.idea || "").slice(0, 80)}"`,
      `Current phase: **${state.current_phase}**`,
      "",
      "**Progress:**",
      ...phases.map(p => `  ${completed.has(p) ? "✓" : "○"} /${p}`),
    ];
    if (state.generated_config) {
      const tier = state.generated_config.complexity_tier || "?";
      const preset = state.generated_config.preset || "?";
      lines.push("", `Auto-config: **${tier}** tier (preset: ${preset}) — config.yaml written`);
    }
    if (state.review_score) {
      lines.push("", `Review score: **${state.review_score.overall_score}/10**`);
      if (state.review_score.feedback) lines.push(`Feedback: ${state.review_score.feedback.slice(0, 200)}`);
    }
    if (state.ship_log?.shipped) {
      lines.push("", `✅ Shipped at: ${state.ship_log.deployed_at}`);
      lines.push(`Rollback: \`${state.ship_log.rollback_ref}\``);
    }
    return { content: [{ type: "text", text: lines.join("\n") }] };
  } catch (e) {
    return { content: [{ type: "text", text: `get_pipeline failed: ${e.message}` }] };
  }
};
_readHandlers.set("get_pipeline", _handle_get_pipeline);
server.registerTool(
  "get_pipeline",
  {
    title: "Get Pipeline",
    description: "Return the current state of a Ship Chain pipeline — current phase, completed phases, artifact sizes, and phase-specific results (test pass/fail, review score, ship log).",
    inputSchema: {
      pipeline_id: z.string().describe("Pipeline ID to inspect (e.g. RA-547 or abc12345)"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  _handle_get_pipeline
);

// ── Tool: perplexity_research ─────────────────────────────────────────────────
server.registerTool(
  "perplexity_research",
  {
    title: "Perplexity Research",
    description:
      "RA-929: Real-time web research via the Perplexity Sonar API. " +
      "Use for CVE/dependency vulnerability lookups (model='sonar', domains=['nvd.nist.gov','github.com/advisories']), " +
      "architecture research before spec_idea/plan_build (model='sonar-pro'), " +
      "or any question requiring up-to-date information beyond the training cutoff. " +
      "Returns the answer text plus cited sources. Requires PERPLEXITY_API_KEY in env.",
    inputSchema: {
      query:   z.string().min(1).describe("Research question or CVE lookup query"),
      model:   z.enum(["sonar", "sonar-pro"]).optional().default("sonar")
               .describe("sonar = fast ($0.25/M tokens); sonar-pro = deep research ($2.50/M tokens)"),
      domains: z.array(z.string()).optional().default([])
               .describe("Restrict search to these domains (e.g. ['nvd.nist.gov','github.com/advisories'])"),
      recency: z.enum(["day", "week", "month", "year"]).optional().default("month")
               .describe("Limit results to this recency window"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: false },
  },
  async ({ query, model = "sonar", domains = [], recency = "month" }) => {
    /** RA-929: Perplexity Sonar query — real-time research with citations. */
    if (!PERPLEXITY_API_KEY) {
      return {
        content: [{
          type: "text",
          text: "PERPLEXITY_API_KEY not set. Add it to the MCP env block in claude_desktop_config.json:\n" +
                "  \"env\": { \"PERPLEXITY_API_KEY\": \"pplx-...\" }\n" +
                "Get a key at: https://www.perplexity.ai/settings/api",
        }],
      };
    }

    try {
      const body = JSON.stringify({
        model,
        messages: [{ role: "user", content: query }],
        search_recency_filter: recency,
        ...(domains.length > 0 && { search_domain_filter: domains }),
        return_citations: true,
      });

      const response = await new Promise((resolve, reject) => {
        const req = https.request(
          {
            hostname: "api.perplexity.ai",
            path: "/chat/completions",
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${PERPLEXITY_API_KEY}`,
              "Content-Length": Buffer.byteLength(body),
            },
          },
          (res) => {
            let data = "";
            res.on("data", (chunk) => { data += chunk; });
            res.on("end", () => resolve({ status: res.statusCode, body: data }));
          }
        );
        req.on("error", reject);
        req.setTimeout(30000, () => { req.destroy(new Error("Perplexity request timed out after 30s")); });
        req.write(body);
        req.end();
      });

      if (response.status !== 200) {
        return { content: [{ type: "text", text: `Perplexity API error ${response.status}: ${response.body.slice(0, 300)}` }] };
      }

      const data = JSON.parse(response.body);
      const answer = data.choices?.[0]?.message?.content || "(no answer)";
      const citations = (data.citations || []).slice(0, 8);

      const lines = [
        `**Perplexity ${model} — "${query.slice(0, 80)}"**`,
        "",
        answer,
      ];
      if (citations.length > 0) {
        lines.push("", "**Sources:**");
        citations.forEach((url, i) => lines.push(`${i + 1}. ${url}`));
      }
      return { content: [{ type: "text", text: lines.join("\n") }] };
    } catch (e) {
      return { content: [{ type: "text", text: `perplexity_research failed: ${e.message}` }] };
    }
  }
);

// ── Tool: run_parallel ────────────────────────────────────────────────────────
server.registerTool(
  "run_parallel",
  {
    title: "Run Parallel",
    description:
      "RA-933: Execute multiple read-only Pi-CEO tools concurrently in a single round-trip. " +
      "Pass an array of {tool_name, args} objects. Read-only tools run in parallel via Promise.all; " +
      "write tools are rejected. Returns an array of results in the same order as the input. " +
      `Supported tools: ${[...READ_ONLY_TOOLS].join(", ")}`,
    inputSchema: {
      calls: z
        .array(
          z.object({
            tool_name: z.string().describe("Tool name (must be in READ_ONLY_TOOLS)"),
            args: z.record(z.unknown()).optional().describe("Tool arguments (pass {} if none)"),
          })
        )
        .min(1)
        .max(10)
        .describe("List of tool calls to execute concurrently (max 10)"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: false },
  },
  async ({ calls }) => {
    /** RA-933: parallel dispatch — read-only tools only. */
    const results = await Promise.all(
      calls.map(async ({ tool_name, args = {} }) => {
        if (!READ_ONLY_TOOLS.has(tool_name)) {
          return {
            tool_name,
            error: `'${tool_name}' is not in READ_ONLY_TOOLS — only read-only tools may run in parallel`,
          };
        }
        const handler = _readHandlers.get(tool_name);
        if (!handler) {
          return { tool_name, error: `Handler for '${tool_name}' not registered in _readHandlers` };
        }
        try {
          const result = await handler(args);
          const text = result?.content?.[0]?.text ?? JSON.stringify(result);
          return { tool_name, result: text };
        } catch (e) {
          return { tool_name, error: e.message };
        }
      })
    );
    return {
      content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
    };
  }
);

// ── Tool: margot_turn (RA-1871) ────────────────────────────────────────────────
// Drives one Margot turn through the Wave-4/5 swarm.margot_bot.handle_turn
// pipeline (operating context + 2-phase research + Board triggers + 3-tier
// provider routing). Caller (Hermes) is responsible for delivering the
// returned `reply` to Telegram — the route runs handle_turn with _send=False.
//
// Env required:
//   PI_CEO_API_BASE        — production API base, e.g. https://pi-dev-ops-production.up.railway.app
//   TAO_WEBHOOK_SECRET     — same secret already in Railway, used as X-Pi-CEO-Secret
const PI_CEO_API_BASE  = (process.env.PI_CEO_API_BASE || "").replace(/\/+$/, "");
const TAO_WEBHOOK_SECRET = process.env.TAO_WEBHOOK_SECRET || "";

server.registerTool(
  "margot_turn",
  {
    title: "Margot Turn (Wave-4/5 enriched)",
    description:
      "RA-1871: Run one Margot turn through Pi-CEO's swarm.margot_bot.handle_turn — " +
      "loads conversation history + senior-bot operating context + Board state, runs " +
      "2-phase research if [RESEARCH] sentinels appear, parses [BOARD-TRIGGER] markers, " +
      "and returns the user-facing reply. Use this when answering as Margot in a " +
      "Telegram-style chat where you want the full Wave-4/5 enrichment instead of a " +
      "stateless Anthropic call. Caller delivers the returned reply themselves.",
    inputSchema: {
      chat_id: z.string().describe("Telegram chat_id (string)"),
      user_text: z.string().min(1).max(4000).describe("The user's message text"),
      message_id: z.string().optional().describe("Telegram message_id for traceability"),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ chat_id, user_text, message_id }) => {
    if (!PI_CEO_API_BASE) {
      throw new Error("PI_CEO_API_BASE not set in MCP env (claude_desktop_config.json or shell)");
    }
    if (!TAO_WEBHOOK_SECRET) {
      throw new Error("TAO_WEBHOOK_SECRET not set in MCP env");
    }
    const body = JSON.stringify({
      chat_id: String(chat_id),
      user_text,
      ...(message_id ? { message_id: String(message_id) } : {}),
    });
    const url = new URL(`${PI_CEO_API_BASE}/api/margot/turn`);
    return new Promise((resolve, reject) => {
      const req = https.request(
        {
          method: "POST",
          host: url.host,
          path: url.pathname + url.search,
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body),
            "X-Pi-CEO-Secret": TAO_WEBHOOK_SECRET,
          },
          // handle_turn can be slow on Phase 2 (deep_research). The Pi-CEO
          // route caps at 120s; give the HTTP client 130s slack.
          timeout: 130_000,
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => (data += chunk));
          res.on("end", () => {
            if (res.statusCode < 200 || res.statusCode >= 300) {
              return reject(new Error(`Pi-CEO /api/margot/turn HTTP ${res.statusCode}: ${data}`));
            }
            try {
              const parsed = JSON.parse(data);
              resolve({
                content: [
                  { type: "text", text: parsed.reply || "" },
                  {
                    type: "text",
                    text: `\n[turn_id=${parsed.turn_id} cost_usd=${parsed.cost_usd} ` +
                      `research_called=${parsed.research_called} ` +
                      `board_session_ids=${JSON.stringify(parsed.board_session_ids)}]`,
                  },
                ],
              });
            } catch (e) {
              reject(new Error(`Pi-CEO /api/margot/turn returned non-JSON: ${data.slice(0, 200)}`));
            }
          });
        }
      );
      req.on("error", reject);
      req.on("timeout", () => {
        req.destroy(new Error("Pi-CEO /api/margot/turn timed out after 130s"));
      });
      req.write(body);
      req.end();
    });
  }
);

// ── Tool: code_execute (RA-1458) ──────────────────────────────────────────────
// Per Anthropic's 2025 "Code Execution with MCP" paper — 98.7% token savings
// measured. Instead of "Claude asks linear_list_issues → 500 rows flow through
// context", Claude writes a filter script against a whitelisted API surface,
// the MCP server runs it in a sandboxed vm, and only the filtered result
// crosses the wire.

/**
 * Build a whitelisted API surface for the code_execute sandbox.
 * Scope gates which objects are exposed to the user's script.
 */
function _buildCodeExecuteScope(scope) {
  const api = {};

  const linearApi = {
    // One-shot GraphQL passthrough for flexible queries. Read-only in
    // practice because we do not expose mutation helpers here.
    gql: (query, variables) => linearGql(query, variables),
    // Convenience: list issues with a filter object (all fields optional).
    list: async ({ state, priority, limit = 50, assigneeEmail } = {}) => {
      const filter = {};
      if (state) filter.state = { name: { eq: state } };
      if (typeof priority === "number") filter.priority = { eq: priority };
      if (assigneeEmail) filter.assignee = { email: { eq: assigneeEmail } };
      const q = `query($filter:IssueFilter,$first:Int){ issues(filter:$filter,first:$first){ nodes{ id identifier title state{ name } priority assignee{ name email } project{ name } team{ key } url updatedAt } } }`;
      const r = await linearGql(q, { filter, first: Math.min(limit, 250) });
      return r?.data?.issues?.nodes || [];
    },
    // Fetch a single issue by identifier (e.g. "RA-1234").
    get: async (identifier) => {
      const q = `query($id:String!){ issue(id:$id){ id identifier title description state{ name } priority assignee{ name email } project{ name } team{ key } url createdAt updatedAt completedAt } }`;
      const r = await linearGql(q, { id: identifier });
      return r?.data?.issue || null;
    },
  };

  const harnessApi = {
    read: (filename) => readHarness(filename),
    list: () => {
      if (!fs.existsSync(HARNESS_DIR)) return [];
      return fs.readdirSync(HARNESS_DIR).filter((f) => !f.startsWith("."));
    },
    exists: (filename) => fs.existsSync(path.join(HARNESS_DIR, filename)),
  };

  if (scope === "linear" || scope === "all") api.linear = linearApi;
  if (scope === "harness" || scope === "all") api.harness = harnessApi;
  return api;
}

server.registerTool(
  "code_execute",
  {
    title: "Execute JavaScript against whitelisted Pi-CEO APIs",
    description:
      "RA-1458: Run a JavaScript snippet inside a sandboxed vm context that has " +
      "access to whitelisted Pi-CEO APIs (Linear + harness filesystem, read-only). " +
      "Use this instead of `linear_list_issues` / `linear_sync_board` / `get_last_analysis` " +
      "when the raw result would be large — filter/aggregate server-side and return only " +
      "the matches. Measured 90%+ token saving vs raw tool-call results. " +
      "\n\nAvailable globals (by scope):\n" +
      "- `linear.list({state, priority, limit, assigneeEmail})` → array\n" +
      "- `linear.get('RA-1234')` → issue or null\n" +
      "- `linear.gql(query, variables)` → raw GraphQL response\n" +
      "- `harness.read(filename)` → string\n" +
      "- `harness.list()` → array of filenames\n" +
      "- `harness.exists(filename)` → boolean\n" +
      "\nThe script's final expression is the return value. Use `console.log(...)` " +
      "for debug output (returned as `logs`). No `require`, no `fs`, no network outside " +
      "the whitelisted APIs. Timeout defaults to 5000ms, max 30000ms.",
    inputSchema: {
      script: z
        .string()
        .min(1)
        .max(10000)
        .describe("JavaScript to execute. Write an async IIFE for await-using code."),
      scope: z
        .enum(["linear", "harness", "all"])
        .optional()
        .describe("Which APIs to expose (default: all)"),
      timeout_ms: z
        .number()
        .int()
        .min(100)
        .max(30000)
        .optional()
        .describe("Hard timeout in ms (default 5000, max 30000)"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: false },
  },
  async ({ script, scope = "all", timeout_ms = 5000 }) => {
    const logs = [];
    const sandbox = {
      console: {
        log: (...args) => logs.push(args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" ")),
        error: (...args) => logs.push("[error] " + args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" ")),
      },
      ..._buildCodeExecuteScope(scope),
    };

    // Wrap the script so a bare expression becomes the return value of an
    // async function, and so top-level `await` works.
    const wrapped = `(async () => { return (${script}); })()`;

    const ctx = vm.createContext(sandbox);
    const start = Date.now();
    try {
      const resultPromise = vm.runInContext(wrapped, ctx, {
        timeout: timeout_ms,
        displayErrors: true,
      });
      const result = await Promise.race([
        resultPromise,
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error(`code_execute async timeout after ${timeout_ms}ms`)), timeout_ms)
        ),
      ]);
      const elapsed_ms = Date.now() - start;
      const body = {
        result,
        logs,
        elapsed_ms,
        scope,
      };
      return { content: [{ type: "text", text: JSON.stringify(body, null, 2) }] };
    } catch (e) {
      const elapsed_ms = Date.now() - start;
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              { error: e.message, logs, elapsed_ms, scope },
              null,
              2
            ),
          },
        ],
      };
    }
  }
);

// ── Start Server ───────────────────────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Server is now running — the SDK handles all MCP protocol negotiation
  process.stderr.write("Pi CEO MCP Server v3.5.0 started (stdio transport, 26 tools)\n");
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});