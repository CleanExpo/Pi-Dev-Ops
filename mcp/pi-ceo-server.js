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
  version: "3.0.0",
});

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
    return { content: [{ type: "text", text: `${spec}\n\n---\n\n${exec}` }] };
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
    return { content: [{ type: "text", text: notes }] };
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

// ── Start Server ───────────────────────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Server is now running — the SDK handles all MCP protocol negotiation
  process.stderr.write("Pi CEO MCP Server v3.0.0 started (stdio transport)\n");
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});