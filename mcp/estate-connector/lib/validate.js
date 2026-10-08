export class ToolError extends Error {
  constructor(message) {
    super(message);
    this.name = "ToolError";
  }
}

const ID_RE = /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,79}$/;

export function cleanId(value) {
  if (typeof value !== "string" || !ID_RE.test(value)) {
    throw new ToolError("id must be 1-80 letters, numbers, or . _ : -");
  }
  return value;
}

export function cleanText(value, label, max = 2000) {
  if (typeof value !== "string") throw new ToolError(`${label} is required.`);
  const text = value.trim();
  if (!text) throw new ToolError(`${label} is required.`);
  if (text.length > max) throw new ToolError(`${label} must be ${max} characters or fewer.`);
  return text;
}

export function assertSystem(systems, system) {
  if (!systems.has(system)) throw new ToolError("Unknown system.");
  return system;
}
