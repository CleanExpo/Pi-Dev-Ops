// Pure masking for ato-guard: no `$`, so it unit-tests without the kit.
//
// Every string a tool returns is passed through MASKS, in order, before the
// model reads it. Order matters: tokens and bank details first (they contain
// digit runs of their own), then ABN (11 digits) before TFN (8–9), so an ABN is
// never half-masked as a TFN.
//
// Boundaries. A number only matches when it is not part of a longer run: no
// letter, digit, `_`, `.`, `-` or `/` directly before it, and no letter or digit
// (or `.`/`-`/`/` + digit) directly after it. That keeps invoice numbers
// (INV-00012345), hashes, versions, ISO dates and phone numbers out. Grouped
// forms also refuse a neighbouring `<digit><space>`, so `0412 345 678` and
// `+61 2 9876 5432` are left alone.

export type Kind = 'TFN' | 'ABN' | 'BANK' | 'TOKEN'
export type Counts = Partial<Record<Kind, number>>

const B = String.raw`(?<![\w./-])(?<!\d )`
const E = String.raw`(?![\w])(?![./-]\d)(?! \d)`

export const MASKS: ReadonlyArray<readonly [Kind, RegExp]> = [
  // `Bearer <token>`: 16+ token characters, so prose like "Bearer tokens" stays.
  ['TOKEN', /\bBearer\s+[\w\-.~+/]{16,}=*/gi],
  // XERO_ACCESS_TOKEN=…, MY_XERO_TOKEN=…, xero_refresh_token: "…", "xeroToken": "…"
  ['TOKEN', /xero[_-]?[a-z_]*token[a-z_]*["']?\s*[=:]\s*["']?[^\s"'&,;]+/gi],
  // BSB ddd-ddd, then the account number (6–10 digits), optionally labelled.
  ['BANK', new RegExp(
    B + String.raw`\d{3}-\d{3}[\s,:/-]+(?:(?:acc(?:ount)?|a/c)\.?(?:\s*(?:no\.?|number|#))?[\s:#.-]*)?\d{6,10}` + E,
    'gi',
  )],
  ['ABN', new RegExp(B + String.raw`(?:\d{2} \d{3} \d{3} \d{3}|\d{11})` + E, 'g')],
  ['TFN', new RegExp(B + String.raw`(?:\d{3} \d{3} \d{3}|\d{8,9})` + E, 'g')],
]

/** Masks one string, adding what it replaced to `counts`. */
export function maskText(text: string, counts: Counts): string {
  let out = text
  for (const [kind, re] of MASKS) {
    out = out.replace(re, () => {
      counts[kind] = (counts[kind] ?? 0) + 1
      return `[masked:${kind}]`
    })
  }
  return out
}

const MAX_DEPTH = 32

/** Masks every string inside a tool result: strings, arrays and plain objects. */
export function maskValue(value: unknown, counts: Counts, depth = 0): unknown {
  if (typeof value === 'string') return maskText(value, counts)
  if (depth >= MAX_DEPTH || value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) return value.map(v => maskValue(v, counts, depth + 1))
  const proto = Object.getPrototypeOf(value)
  if (proto !== Object.prototype && proto !== null) return value
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = maskValue(v, counts, depth + 1)
  return out
}

/** Total replacements across kinds. */
export function total(counts: Counts): number {
  let n = 0
  for (const v of Object.values(counts)) n += v ?? 0
  return n
}
