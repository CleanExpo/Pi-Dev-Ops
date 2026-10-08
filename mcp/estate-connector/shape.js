const SECRET_VALUE = /^(?:sk-|lin_api_|github_pat_|ghp_|Bearer\s)\S+/i;
const SECRET_KEY = /token|secret|password|authorization|credential/i;

export function scrubText(value) {
  return String(value)
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/\b(?:sk-|lin_api_|github_pat_|ghp_)[A-Za-z0-9_-]+/g, "[redacted]");
}

export function redact(value, depth = 0) {
  if (depth > 6) return null;
  if (Array.isArray(value)) return value.slice(0, 40).map((item) => redact(item, depth + 1));
  if (value && typeof value === "object") {
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      if (SECRET_KEY.test(key) && typeof item === "string") continue;
      out[key] = redact(item, depth + 1);
    }
    return out;
  }
  if (typeof value === "string") {
    if (SECRET_VALUE.test(value)) return "[redacted]";
    return value.length > 2000 ? value.slice(0, 2000) : value;
  }
  return value;
}

export function ok(data) {
  return { content: [{ type: "text", text: JSON.stringify(redact(data), null, 2) }] };
}

export function fail(message) {
  return { isError: true, content: [{ type: "text", text: JSON.stringify({ error: scrubText(message) }) }] };
}

const HEALTH_KEYS = [
  "status", "uptime_s", "sessions", "claude_cli", "anthropic_key", "linear_key",
  "linear_api_key", "autonomy", "disk_free_gb", "version", "vercel_token",
  "github_token", "swarm_enabled", "swarm_shadow", "pi_seo_active",
];

export function trimHealth(body) {
  if (!body || typeof body !== "object") return null;
  const out = {};
  for (const key of HEALTH_KEYS) {
    if (key in body) out[key] = body[key];
  }
  return out;
}

export function trimLive(body) {
  if (!body || typeof body !== "object") return null;
  const sessions = Array.isArray(body.active_sessions) ? body.active_sessions : [];
  return {
    ts: body.ts || null,
    queue: body.queue || null,
    pulse: body.pulse || null,
    active_session_count: sessions.length,
    active_sessions: sessions.slice(0, 10).map((session) => ({
      id: session?.id || null,
      repo: session?.repo || null,
      phase: session?.phase || null,
      elapsed_s: session?.elapsed_s ?? null,
    })),
    observability_ok: body.observability?.ok ?? null,
  };
}

export function queueCounts(items) {
  const counts = { open: 0, claimed: 0, blocked: 0, done: 0, total: items.length };
  for (const item of items) {
    if (item.status in counts) counts[item.status] += 1;
  }
  return counts;
}
