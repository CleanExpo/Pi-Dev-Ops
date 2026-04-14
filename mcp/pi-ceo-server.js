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
 */

const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const fs   = require("fs");
const path = require("path");
const https = require("https");

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

// ── Server Setup ───────────────────────────────────────────────────────────────
const server = new McpServer({
  name: "pi-ceo",
  version: "3.1.0",
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
server.registerTool(
  "get_last_analysis",
  {
    title: "Get Last Pi CEO Analysis",
    description: "Get the full Pi CEO analysis from the last run (spec + executive summary). Use this to answer questions about any recently analysed repository.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
    const spec = readHarness("spec.md");
    const exec = readHarness("executive-summary.md");
    const stale = harnessStalenessBanner();
    return { content: [{ type: "text", text: `${spec}\n\n---\n\n${exec}${stale}` }] };
  }
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

// ── Tool: get_sprint_plan ──────────────────────────────────────────────────────
server.registerTool(
  "get_sprint_plan",
  {
    title: "Get Sprint Plan",
    description: "Get the prioritised sprint plan from the last Pi CEO analysis with full task details.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
    // Prefer dedicated sprint_plan.md; fall back to parsing spec.md
    const sprintPath = path.join(HARNESS_DIR, "sprint_plan.md");
    if (fs.existsSync(sprintPath)) {
      return { content: [{ type: "text", text: fs.readFileSync(sprintPath, "utf8") }] };
    }
    const spec = readHarness("spec.md");
    const match = spec.match(/## Sprint Plan([\s\S]*?)(?:\n##|$)/);
    const sprint = match ? match[1].trim() : spec;
    return { content: [{ type: "text", text: sprint }] };
  }
);

// ── Tool: get_feature_list ─────────────────────────────────────────────────────
server.registerTool(
  "get_feature_list",
  {
    title: "Get Feature List",
    description: "Get the full feature list JSON from the last Pi CEO analysis.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
    const features = readHarness("feature_list.json");
    return { content: [{ type: "text", text: features }] };
  }
);

// ── Tool: list_harness_files ───────────────────────────────────────────────────
server.registerTool(
  "list_harness_files",
  {
    title: "List Harness Files",
    description: "List all files in the .harness/ directory from the last Pi CEO analysis run.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
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
  }
);

// ── Tool: get_zte_score ────────────────────────────────────────────────────────
server.registerTool(
  "get_zte_score",
  {
    title: "Get ZTE Maturity Score",
    description: "Get the Zero Touch Execution maturity score and leverage point breakdown from the last analysis.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
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
  }
);

// ── Tool: linear_list_issues ───────────────────────────────────────────────────
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
  async ({ status, limit }) => {
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
  }
);

// ── Tool: linear_create_issue ──────────────────────────────────────────────────
server.registerTool(
  "linear_create_issue",
  {
    title: "Create Linear Issue",
    description: "Create a new issue in the Pi-Dev-Ops Linear project. Provide title, description, priority (1=Urgent, 2=High, 3=Normal, 4=Low), and optional labels.",
    inputSchema: {
      title: z.string().min(1).describe("Issue title"),
      description: z.string().optional().describe("Issue description in Markdown"),
      priority: z.number().int().min(0).max(4).default(3).describe("Priority: 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low"),
      labels: z.array(z.string()).optional().describe("Array of label names to apply"),
      status: z.string().optional().describe("Initial status: backlog, todo, in_progress. Defaults to backlog."),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
  },
  async ({ title, description, priority, labels, status }) => {
    const team = await findTeamId();
    const project = await findProjectId();

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
        searchIssues(query: "${identifier}", first: 1) {
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
  async ({ query, limit }) => {
    const project = await findProjectId();

    const data = await linearGql(`{
      searchIssues(query: "${query.replace(/"/g, '\\"')}", first: ${limit}) {
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
  }
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
        orderBy: priority
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
server.registerTool(
  "linear_status",
  {
    title: "Linear Auth Status",
    description: "Check if the Linear API key is configured and verify it can reach the Linear API. Use this to diagnose auth issues before running other linear_* tools.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
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
  }
);

// ── Tool: get_project_health ──────────────────────────────────────────────────
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
  async ({ project_id }) => {
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
  }
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
server.registerTool(
  "get_monitor_digest",
  {
    title: "Get Monitor Digest",
    description: "Return the latest Pi-SEO portfolio health monitor digest. Shows portfolio health score, per-project deltas, regressions, systemic issues, and alerts.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  },
  async () => {
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
  }
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
  async ({ pipeline_id }) => {
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
  }
);

// ── Start Server ───────────────────────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Server is now running — the SDK handles all MCP protocol negotiation
  process.stderr.write("Pi CEO MCP Server v3.1.0 started (stdio transport, 22 tools)\n");
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});