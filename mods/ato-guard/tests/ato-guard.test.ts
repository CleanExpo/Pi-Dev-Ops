import { describe, expect, mock, test } from 'claude-code/testing'

const ATO = 'https://github.com/CleanExpo/ATO.git'
const AUDIT = '/home/test/.ato-guard/audit.jsonl'

type Opts = { remote?: string | null; result?: unknown; files?: Record<string, string> }

/** Stubs every call the mod makes; returns what reached the tool and what was written. */
function harness(on: any, opts: Opts = {}) {
  const files: Record<string, string> = { ...(opts.files ?? {}) }
  const ran: string[] = []
  mock.clock(on, { now: 1_700_000_000_000 })
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }))
  on('session.repo', () => ({ value: opts.remote === null ? null : { root: '/w', remote: opts.remote ?? ATO, internal: false } }))
  on('fs.exists', ($: unknown, e: { path: string }) => ({ value: e.path in files }))
  on('fs.read', ($: unknown, e: { path: string }) => (e.path in files ? { value: files[e.path] } : { deny: 'ENOENT' }))
  on('fs.write', ($: unknown, e: { path: string; text?: string; content?: string }) => {
    files[e.path] = e.text ?? e.content ?? ''
    return { value: undefined }
  })
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  on('tool.call', ($: unknown, e: { tool: string }) => {
    ran.push(e.tool)
    return { result: opts.result ?? 'ok' }
  })
  return { files, ran }
}

function auditLines(files: Record<string, string>): Record<string, unknown>[] {
  return (files[AUDIT] ?? '').split('\n').filter(Boolean).map(l => JSON.parse(l) as Record<string, unknown>)
}

describe('masking before the model reads', () => {
  test('a tool result is masked and the masking is audited', async ($, on) => {
    const { files } = harness(on, { result: 'Client TFN 564 897 586, ABN 51 824 753 556' })
    const out = await $.tool.call({ tool: 'Read', file_path: 'clients.csv' })
    expect(out.result).toBe('Client TFN [masked:TFN], ABN [masked:ABN]')
    expect(auditLines(files)).toEqual([
      { at: '2023-11-14T22:13:20.000Z', session: 'sess-1', tool: 'Read', decision: 'masked:2', counts: { TFN: 1, ABN: 1 } },
    ])
  })

  test('structured results are masked string by string', async ($, on) => {
    harness(on, { result: { content: [{ type: 'text', text: 'BSB 062-000 12345678' }] } })
    const out = await $.tool.call({ tool: 'mcp__files__read_file', path: 'bank.txt' })
    expect(out.result).toEqual({ content: [{ type: 'text', text: 'BSB [masked:BANK]' }] })
  })

  test('a result with nothing to mask comes back as it was, unaudited', async ($, on) => {
    const { files } = harness(on, { result: 'invoice INV-000123 dated 2026-10-06, call 0412 345 678' })
    const out = await $.tool.call({ tool: 'Bash', command: 'cat notes.txt' })
    expect(out.result).toBe('invoice INV-000123 dated 2026-10-06, call 0412 345 678')
    expect(files[AUDIT]).toBeUndefined()
  })
})

describe('blocking writes', () => {
  test('a Xero POST is denied without running, and audited', async ($, on) => {
    const { files, ran } = harness(on)
    const out = await $.tool.call({ tool: 'Bash', command: 'curl -X POST https://api.xero.com/api.xro/2.0/Invoices -d @inv.json' })
    expect(out.deny).toMatch(/^ato-guard: /)
    expect(ran).toEqual([])
    expect(auditLines(files)).toEqual([
      { at: '2023-11-14T22:13:20.000Z', session: 'sess-1', tool: 'Bash', decision: 'denied', counts: {} },
    ])
  })

  test('a lodgement call is denied', async ($, on) => {
    const { ran } = harness(on)
    const out = await $.tool.call({ tool: 'mcp__ato__sbr_lodge_bas', period: '2026Q1' })
    expect(out.deny).toMatch(/^ato-guard: .*lodge/)
    expect(ran).toEqual([])
  })

  test('a read passes through untouched', async ($, on) => {
    const { files, ran } = harness(on, { result: '{"Invoices":[]}' })
    const out = await $.tool.call({ tool: 'mcp__xero__list_invoices', status: 'DRAFT' })
    expect(out).toEqual({ result: '{"Invoices":[]}' })
    expect(ran).toEqual(['mcp__xero__list_invoices'])
    expect(files[AUDIT]).toBeUndefined()
  })
})

describe('audit', () => {
  test('the audit line holds no digits, text or command from the input', async ($, on) => {
    const { files } = harness(on, { result: 'TFN 564 897 586 for jane@example.com' })
    await $.tool.call({ tool: 'Bash', command: 'grep -r 564897586 private/' })
    const raw = files[AUDIT]
    for (const s of ['564', '897', '586', 'jane', 'private', 'grep']) expect(raw).not.toContain(s)
  })

  test('appends to an existing audit file', async ($, on) => {
    const { files } = harness(on, { files: { [AUDIT]: '{"old":1}\n' } })
    await $.tool.call({ tool: 'mcp__xero__create_invoice', contact: 'x' })
    const lines = files[AUDIT].split('\n').filter(Boolean)
    expect(lines.length).toBe(2)
    expect(lines[0]).toBe('{"old":1}')
  })

  test('past 3 MiB the file rolls to audit-<date>.jsonl', async ($, on) => {
    const big = 'x'.repeat(3 * 1024 * 1024) + '\n'
    const { files } = harness(on, { files: { [AUDIT]: big } })
    await $.tool.call({ tool: 'mcp__xero__create_invoice', contact: 'x' })
    expect(files['/home/test/.ato-guard/audit-2023-11-14.jsonl']).toBe(big)
    expect(auditLines(files).length).toBe(1)
  })

  test('an audit failure never breaks the tool call', async ($, on) => {
    mock.clock(on, { now: 1_700_000_000_000 })
    mock.env(on, { HOME: '/home/test' })
    on('session.id', () => ({ value: 'sess-1' }))
    on('session.repo', () => ({ value: { root: '/w', remote: ATO, internal: false } }))
    on('fs.exists', () => ({ deny: 'disk on fire' }))
    on('fs.read', () => ({ deny: 'disk on fire' }))
    on('fs.write', () => ({ deny: 'disk on fire' }))
    on('process.run', () => ({ deny: 'disk on fire' }))
    on('tool.call', () => ({ result: 'TFN 564 897 586' }))
    const out = await $.tool.call({ tool: 'Read', file_path: 'a.txt' })
    expect(out.result).toBe('TFN [masked:TFN]')
    const denied = await $.tool.call({ tool: 'Bash', command: 'npm run lodge' })
    expect(denied.deny).toMatch(/^ato-guard: /)
  })
})

describe('inert outside the ATO repository', () => {
  test('another repository: nothing masked, nothing denied, nothing written', async ($, on) => {
    const { files, ran } = harness(on, { remote: 'https://github.com/CleanExpo/pi-ceo-operator-mcp.git', result: 'TFN 564 897 586' })
    const out = await $.tool.call({ tool: 'Read', file_path: 'a.txt' })
    expect(out.result).toBe('TFN 564 897 586')
    const post = await $.tool.call({ tool: 'Bash', command: 'curl -X POST https://api.xero.com/x' })
    expect(post.deny).toBeUndefined()
    expect(ran).toEqual(['Read', 'Bash'])
    expect(Object.keys(files)).toEqual([])
  })

  test('no repository at all', async ($, on) => {
    const { ran } = harness(on, { remote: null })
    const out = await $.tool.call({ tool: 'mcp__xero__create_invoice', contact: 'x' })
    expect(out.deny).toBeUndefined()
    expect(ran).toEqual(['mcp__xero__create_invoice'])
  })
})
