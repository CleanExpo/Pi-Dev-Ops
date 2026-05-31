// src/lib/integrations/onepassword/client.ts
// Pull NAMES-ONLY from 1Password Connect server. If Connect isn't set up,
// fall back to the `op` CLI via execFileSync (runs on server-side only).
// NEVER reads item values — only titles, categories, and last-modified timestamps.
// execFileSync (not execSync) — args passed as an array, no shell, no
// injection surface even if a vault name contains shell metacharacters.

import { execFileSync } from "node:child_process";

const CONNECT_HOST = process.env.OP_CONNECT_HOST;
const CONNECT_TOKEN = process.env.OP_CONNECT_TOKEN;

export interface OPItemIndex {
  vault: string;
  item_name: string;
  category: string;
  last_modified: string | null;
}

// Vaults are configured per-environment. Empty list → graceful no-op sync.
const VAULTS: string[] = (process.env.OP_VAULTS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const DEFAULT_VAULTS = [
  "Unite-Group-Infrastructure",
  "RestoreAssist",
  "Carsi",
  "CCW-CRM",
  "Synthex",
  "Email-Accounts",
  "Personal",
];

export function configuredVaults(): string[] {
  return VAULTS.length > 0 ? VAULTS : DEFAULT_VAULTS;
}

interface CliItem {
  title: string;
  category: string;
  updated_at: string;
}

/**
 * List items in a single vault via the `op` CLI. Throws on failure so the
 * caller can attribute the error to a specific vault.
 */
export async function listItemsInVaultViaCli(vault: string): Promise<OPItemIndex[]> {
  // execFileSync with arg array — no shell, no injection via vault name.
  const out = execFileSync(
    "op",
    ["item", "list", "--vault", vault, "--format", "json"],
    { encoding: "utf-8" }
  );
  const parsed: CliItem[] = JSON.parse(out);
  return parsed.map((it) => ({
    vault,
    item_name: it.title,
    category: it.category,
    last_modified: it.updated_at ?? null,
  }));
}

interface ConnectVault {
  id: string;
  name: string;
}

interface ConnectItem {
  title: string;
  category: string;
  updatedAt: string;
}

async function connectFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${CONNECT_HOST}${path}`, {
    headers: { Authorization: `Bearer ${CONNECT_TOKEN}` },
  });
  if (!res.ok) {
    throw new Error(`1Password Connect ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

/**
 * List items in a single vault via the 1Password Connect API. The caller
 * resolves the vault name → id mapping once and passes the id here.
 */
export async function listItemsInVaultViaConnect(vault: {
  id: string;
  name: string;
}): Promise<OPItemIndex[]> {
  const items = await connectFetch<ConnectItem[]>(`/v1/vaults/${vault.id}/items`);
  return items.map((it) => ({
    vault: vault.name,
    item_name: it.title,
    category: it.category,
    last_modified: it.updatedAt ?? null,
  }));
}

export async function listConnectVaults(): Promise<ConnectVault[]> {
  if (!CONNECT_HOST || !CONNECT_TOKEN) {
    throw new Error("OP_CONNECT_HOST / OP_CONNECT_TOKEN not configured");
  }
  return connectFetch<ConnectVault[]>("/v1/vaults");
}

export function hasConnect(): boolean {
  return Boolean(CONNECT_HOST && CONNECT_TOKEN);
}
