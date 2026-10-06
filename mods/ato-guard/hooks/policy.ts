// Pure mod-load policy for ato-guard: no `$`, so it unit-tests without the kit.
//
// In the ATO repository, ato-guard refuses (at `plugin.register`) any other
// non-built-in mod that hooks an event able to rewrite what Claude runs or
// reads, before that mod loads:
//   tool.call, tool.check, tool.describe   rewrite, approve or re-describe tool calls
//   prompt.*                               rewrite prompts, system prompt, context
//   classic.PreToolUse, classic.PostToolUse  settings-hook events on tool calls
//   engine.create                          change the mods API other mods receive
// `e.uses.events` holds the patterns as the mod wrote them (`tool.call`, `*`,
// `classic.*`, `prompt.*`, `!tool.describe`), so wildcards are expanded here.
//
// ATO_GUARD_ALLOW_MODS (comma list of plugin names or `<name>@<marketplace>` ids,
// default `mc-lane`) exempts a mod from the `tool.call` rule only. mc-lane hooks
// tool.call to read tool names and timings; an allowed mod that hooks any other
// listed event is still refused.

const EXACT = ['tool.call', 'tool.check', 'tool.describe', 'classic.PreToolUse', 'classic.PostToolUse', 'engine.create']
const PREFIX = 'prompt.'

/** What ATO_GUARD_ALLOW_MODS names. Unset → the default; set but empty → nobody. */
export const DEFAULT_ALLOW = ['mc-lane']

export function parseAllow(raw: string | undefined): string[] {
  if (raw === undefined) return [...DEFAULT_ALLOW]
  return raw.split(',').map(s => s.trim()).filter(s => s.length > 0)
}

function forbidden(event: string): boolean {
  return EXACT.includes(event) || event.startsWith(PREFIX)
}

/**
 * The rewriting events one `on(...)` pattern reaches: itself when it is one,
 * every listed event for `*`, those under the prefix for `noun.*`. A `!`
 * exclusion hooks nothing. A matcher written in braces (`tool.call{tool=Bash}`)
 * still hooks the event.
 */
export function rewritingHits(pattern: string): string[] {
  const p = pattern.replace(/\{.*\}$/, '').trim()
  if (p === '' || p.startsWith('!')) return []
  if (p === '*') return [...EXACT, 'prompt.*']
  if (p.endsWith('.*')) {
    const stem = p.slice(0, -1) // keeps the dot: 'classic.'
    if (PREFIX.startsWith(stem) || stem.startsWith(PREFIX)) return [p]
    return EXACT.filter(ev => ev.startsWith(stem))
  }
  return forbidden(p) ? [p] : []
}

export type ModFacts = {
  name: string
  provenance: string
  tier: string
  events: readonly string[]
}

/**
 * Why this mod must not load in the ATO repository, or null to let it load.
 * Built-in mods always load. An allowed mod may still hook `tool.call` (and
 * nothing else on the list).
 */
export function refuseReason(mod: ModFacts, allow: readonly string[]): string | null {
  if (mod.tier === 'builtin') return null
  const allowed = allow.includes(mod.name) || allow.includes(mod.provenance)
  const hits = new Set<string>()
  for (const pattern of mod.events) {
    for (const hit of rewritingHits(pattern)) {
      if (!(allowed && hit === 'tool.call')) hits.add(hit)
    }
  }
  if (hits.size === 0) return null
  return (
    `in the ATO repository mods may not rewrite tool calls, prompts or the mods API; ` +
    `${mod.name} hooks ${[...hits].join(', ')}. ` +
    'A mod that only reads tool calls can be allowed by name in ATO_GUARD_ALLOW_MODS (tool.call only).'
  )
}
