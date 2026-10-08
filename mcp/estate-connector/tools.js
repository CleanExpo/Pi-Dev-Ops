import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerReadTools } from "./reads.js";
import { registerWriteTools } from "./writes.js";

export const READ_TOOL_NAMES = [
  "unite_status",
  "unite_health",
  "unite_projects",
  "unite_queue",
  "unite_deployments",
  "pidevops_status",
  "pidevops_health",
  "pidevops_projects",
  "pidevops_queue",
  "pidevops_deployments",
  "mc_status",
  "mc_health",
  "mc_projects",
  "mc_queue",
  "coord_list_activity",
  "coord_list_audit",
];

export const WRITE_TOOL_NAMES = [
  "coord_post_note",
  "mc_update_queue_item",
  "mc_claim_work",
  "mc_release_work",
];

export function buildMcpServer(ctx) {
  const server = new McpServer({ name: "estate-connector", version: "1.0.0" });
  registerReadTools(server, ctx);
  registerWriteTools(server, ctx);
  return server;
}
