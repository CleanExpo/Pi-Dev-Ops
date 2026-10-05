// Pure deny rules and scope for ato-guard: no `$`, so they unit-test without the kit.
//
// decide() returns a reason to refuse a tool call, or null to let it run. It
// refuses writes only; every read passes untouched. Rules:
//   xero-http   Bash that sends a write to api.xero.com (-X/--request POST|PUT|
//               PATCH|DELETE, or a body via -d/--data*/--json/-F/--form)
//   xero-mcp    an mcp__*xero* tool whose final name segment does not start
//               with get|list|search|read
//   lodgement   Bash, or an MCP tool name / target field, that mentions SBR or
//               lodging together with a write verb (post, put, patch, submit,
//               send, create, delete, or "lodge" itself)
// Matching is case-insensitive, except curl's short flags (`-d` writes a body,
// `-D` dumps headers; `-F` is a form, `-f` is fail-fast).
//
// Bash is checked one command segment at a time (split on ; && || | & and
// newlines). A segment whose program only reads or edits local text (git, grep,
// cat, …) is skipped, so `git commit -m "fix lodgement submit"` or
// `grep -rn "api.xero.com" -d skip` in the ATO repository still run.

const READ_PREFIX = /^(?:get|list|search|read)/i
const XERO_HOST = /api\.xero\.com/i
const WRITE_METHOD = /(?:^|\s)(?:-X|--request|--method)(?:\s+|=)?['"]?(?:POST|PUT|PATCH|DELETE)\b/i
const HTTPIE_WRITE = /(?:^|\s)(?:http|https|xh)\s+(?:POST|PUT|PATCH|DELETE)\b/i
const DATA_FLAG = /(?:^|\s)(?:-d|--data(?:-raw|-binary|-urlencode|-ascii)?|--json|-F|--form|--post-data|--post-file)(?=$|[\s='"@{])/
const MENTION = /(?<![a-z])(?:sbr2?|lodge|lodges|lodged|lodging|lodgements?|lodgments?)(?![a-z])/i
const WRITE_VERB = /(?<![a-z])(?:post|put|patch|submit|send|create|delete|lodge)(?![a-z])/i
const LOCAL_PROGRAMS = new Set([
  'git', 'grep', 'egrep', 'fgrep', 'rg', 'ag', 'cat', 'bat', 'less', 'more', 'head', 'tail',
  'ls', 'tree', 'wc', 'echo', 'printf', 'cd', 'pwd', 'diff', 'sed',
])
const TARGET_FIELDS = ['url', 'endpoint', 'method', 'action', 'operation', 'path', 'uri']

/** "submitLodgement" → "submit Lodgement", so word boundaries see camelCase. */
function words(text: string): string {
  return text.replace(/([a-z0-9])([A-Z])/g, '$1 $2')
}

function program(segment: string): string {
  const tokens = segment.trim().split(/\s+/).filter(t => !/^[A-Za-z_][A-Za-z0-9_]*=/.test(t))
  const first = tokens[0] === 'sudo' || tokens[0] === 'env' ? tokens[1] : tokens[0]
  return (first ?? '').replace(/^.*\//, '').replace(/^['"(]+/, '')
}

function writes(text: string): boolean {
  return WRITE_METHOD.test(text) || HTTPIE_WRITE.test(text) || DATA_FLAG.test(text)
}

function bashReason(command: string): string | null {
  for (const segment of command.split(/\|\||&&|[;|\n]|&(?=\s|$)/)) {
    // A command substitution can run anything, so it never counts as local.
    if (LOCAL_PROGRAMS.has(program(segment)) && !/\$\(|`/.test(segment)) continue
    if (XERO_HOST.test(segment) && writes(segment)) {
      return 'writes to the Xero API are blocked in the ATO repository. Read-only (GET) calls are allowed; ask the user to make this change in Xero themselves.'
    }
    const w = words(segment)
    if (MENTION.test(w) && (WRITE_VERB.test(w) || writes(segment))) {
      return 'SBR / ATO lodgement writes are blocked in the ATO repository. Nothing may be lodged or submitted from a Claude Code session; ask the user to lodge it themselves.'
    }
  }
  return null
}

function mcpReason(tool: string, input: Record<string, unknown>): string | null {
  const final = tool.split('__').pop() ?? ''
  if (/xero/i.test(tool) && !READ_PREFIX.test(final)) {
    return `${tool} is not a read (get/list/search/read), and Xero writes are blocked in the ATO repository. Ask the user to make this change in Xero themselves.`
  }
  const name = words(tool)
  const nameHit = MENTION.test(name) && WRITE_VERB.test(name) && !READ_PREFIX.test(final)
  const fields = TARGET_FIELDS.map(k => input[k]).filter((v): v is string => typeof v === 'string').join(' ')
  const target = words(fields)
  const fieldHit = MENTION.test(target) && (WRITE_VERB.test(target) || writes(fields))
  if (nameHit || fieldHit) {
    return 'SBR / ATO lodgement writes are blocked in the ATO repository. Nothing may be lodged or submitted from a Claude Code session; ask the user to lodge it themselves.'
  }
  return null
}

/** Why this call must not run, or null. `input` is the tool call event (arguments are its fields). */
export function decide(tool: string, input: Record<string, unknown>): string | null {
  if (tool === 'Bash') return typeof input.command === 'string' ? bashReason(input.command) : null
  if (tool.startsWith('mcp__')) return mcpReason(tool, input)
  return null
}

/** The repository name from a git remote URL (`ATO` from …/CleanExpo/ATO.git), or undefined. */
export function repoName(remote: string | null | undefined): string | undefined {
  if (!remote) return undefined
  const m = /[:/]([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/.exec(remote.trim())
  return m ? m[1] : undefined
}

/**
 * True for the ATO repository (CleanExpo/ATO) and its namesakes (ato-ai, ATO-…).
 * "ato" must be a whole word of the name, so Calculator, operator and Generator
 * repositories are not in scope.
 */
export function isAtoRemote(remote: string | null | undefined): boolean {
  const name = repoName(remote)
  return name !== undefined && /(?:^|[^a-z0-9])ato(?:[^a-z0-9]|$)/i.test(name)
}
