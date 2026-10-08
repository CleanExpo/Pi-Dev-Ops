export function ok(data) {
  return { content: [{ type: "text", text: JSON.stringify(data) }] };
}

export function fail(message) {
  return {
    isError: true,
    content: [{ type: "text", text: JSON.stringify({ error: message }) }],
  };
}

const SECRET = /token|password|secret|api[_-]?key|authorization/i;

export function redact(value, depth = 0) {
  if (!value || typeof value !== "object" || depth > 4) return value;
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => redact(item, depth + 1));
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    out[key] = SECRET.test(key) ? "[redacted]" : redact(item, depth + 1);
  }
  return out;
}
