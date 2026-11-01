// Canonical serialisation used by goldens and equality checks.
// Object keys sorted recursively, array order preserved (order is meaningful),
// 2-space indent, trailing newline. -0 serialises as 0 (JSON.stringify).

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === 'object') {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = sortKeys(value[key]);
    return out;
  }
  return value;
}

export function canonical(value) {
  return JSON.stringify(sortKeys(value), null, 2) + '\n';
}
