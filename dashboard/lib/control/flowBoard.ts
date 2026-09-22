import { agingTone, classifyLane, flowBoardColumn, type FlowLane } from "@/lib/control/flowLane";

export interface FlowBoardRow {
  id: string;
  title: string;
  url: string;
  lane: FlowLane;
  column: "shipped" | "audit" | "phill" | "aging";
  ageDays: number;
  tone: ReturnType<typeof agingTone>;
  receipts: string;
}

export interface FlowBoardPayload {
  ok: boolean;
  checked_at: string;
  error: string | null;
  awaiting_phill_long: boolean;
  columns: {
    shipped: FlowBoardRow[];
    audit: FlowBoardRow[];
    phill: FlowBoardRow[];
    aging: FlowBoardRow[];
  };
}

export function emptyFlowBoard(error: string | null, ok: boolean): FlowBoardPayload {
  return {
    ok: ok && error === null,
    checked_at: new Date().toISOString(),
    error,
    awaiting_phill_long: false,
    columns: { shipped: [], audit: [], phill: [], aging: [] },
  };
}

const PULL_PATH = /^\/CleanExpo\/[A-Za-z0-9._-]+\/(pull|issues)\/\d+\/?$/;

export function isSafePullUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return (
      parsed.protocol === "https:"
      && parsed.hostname === "github.com"
      && parsed.username === ""
      && parsed.password === ""
      && (parsed.port === "" || parsed.port === "443")
      && PULL_PATH.test(parsed.pathname)
    );
  } catch {
    return false;
  }
}

function isFlowLane(value: unknown): value is FlowLane {
  return value === "flow" || value === "engineer" || value === "founder" || value === "unclassified";
}

function isBoardColumn(value: unknown): value is FlowBoardRow["column"] {
  return value === "shipped" || value === "audit" || value === "phill" || value === "aging";
}

function parseRow(raw: unknown): FlowBoardRow | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Partial<FlowBoardRow>;
  if (typeof row.id !== "string" || !/^PR-\d{1,7}$/.test(row.id)) return null;
  if (typeof row.title !== "string" || typeof row.url !== "string") return null;
  if (!isFlowLane(row.lane) || !isBoardColumn(row.column)) return null;
  if (!Number.isFinite(row.ageDays) || (row.ageDays as number) < 0) return null;
  return {
    id: row.id,
    title: row.title.slice(0, 160).replace(/[<>]/g, ""),
    url: isSafePullUrl(row.url) ? row.url : "#",
    lane: row.lane,
    column: row.column === "shipped" && row.lane === "unclassified" ? "audit" : row.column,
    ageDays: Math.floor(row.ageDays as number),
    tone: agingTone(row.ageDays as number),
    receipts: typeof row.receipts === "string" ? row.receipts.slice(0, 80) : "",
  };
}

export function parseFlowBoardPayload(raw: unknown): FlowBoardPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Partial<FlowBoardPayload>;
  if (!data.columns || typeof data.ok !== "boolean") return null;
  if (typeof data.checked_at !== "string" || Number.isNaN(Date.parse(data.checked_at))) return null;
  const keys = ["shipped", "audit", "phill", "aging"] as const;
  const columns: FlowBoardPayload["columns"] = { shipped: [], audit: [], phill: [], aging: [] };
  for (const key of keys) {
    if (!Array.isArray(data.columns[key])) return null;
    for (const item of data.columns[key] ?? []) {
      const row = parseRow(item);
      if (!row) return null;
      columns[row.column].push(row);
    }
  }
  return {
    ok: data.ok && data.error == null,
    checked_at: data.checked_at,
    error: typeof data.error === "string" ? data.error : null,
    awaiting_phill_long: columns.phill.length >= 3,
    columns,
  };
}

export function ageDaysSince(iso: string, nowMs: number): number {
  const start = Date.parse(iso);
  if (Number.isNaN(start) || nowMs < start) return 7;
  return Math.floor((nowMs - start) / 86_400_000);
}

export function rowFromPull(input: {
  id: string;
  title: string;
  url: string;
  paths: string[];
  labels: string[];
  createdAt: string;
  mergedToday: boolean;
  auditGreen: boolean;
  nowMs: number;
}): FlowBoardRow {
  const lane = classifyLane(input.paths, input.labels);
  const founderGo = input.labels.some((item) => item.toLowerCase() === "founder-go");
  const ageDays = ageDaysSince(input.createdAt, input.nowMs);
  const column = flowBoardColumn({
    lane,
    mergedToday: input.mergedToday,
    auditGreen: input.auditGreen,
    founderGo,
    ageDays,
  });
  const url = isSafePullUrl(input.url) ? input.url : "#";
  const title = input.title.slice(0, 160).replace(/[<>]/g, "");
  return {
    id: input.id.replace(/[^\w-]/g, "").slice(0, 16),
    title,
    url,
    lane,
    column,
    ageDays,
    tone: agingTone(ageDays),
    receipts: lane === "unclassified"
      ? "unclassified — no paths and no lane label"
      : input.mergedToday
        ? input.auditGreen
          ? "audit present"
          : "missing audit receipt"
        : lane,
  };
}

export function assembleFlowBoard(rows: FlowBoardRow[], error: string | null): FlowBoardPayload {
  const columns: FlowBoardPayload["columns"] = {
    shipped: [],
    audit: [],
    phill: [],
    aging: [],
  };
  for (const row of rows) columns[row.column].push(row);
  return {
    ok: error === null,
    checked_at: new Date().toISOString(),
    error,
    awaiting_phill_long: columns.phill.length >= 3,
    columns,
  };
}
