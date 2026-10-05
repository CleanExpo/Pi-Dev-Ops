import { describe, expect, test } from 'claude-code/testing'
import { auditLine, needsRoll, rollName, ROLL_BYTES } from '../hooks/audit'
import { decide, isAtoRemote, repoName } from '../hooks/guard'
import { maskText, maskValue, total, type Counts } from '../hooks/mask'

function mask(text: string): string {
  return maskText(text, {})
}

describe('masking: positives', () => {
  test('TFN, plain and grouped', () => {
    expect(mask('TFN 123456782 on file')).toBe('TFN [masked:TFN] on file')
    expect(mask('tfn: 123 456 782.')).toBe('tfn: [masked:TFN].')
    expect(mask('old TFN 12345678')).toBe('old TFN [masked:TFN]')
  })

  test('ABN, plain and grouped, is never half-masked as a TFN', () => {
    expect(mask('ABN 51 824 753 556')).toBe('ABN [masked:ABN]')
    expect(mask('"abn":"51824753556"')).toBe('"abn":"[masked:ABN]"')
  })

  test('BSB with account number, with or without a label', () => {
    expect(mask('pay 062-000 12345678 today')).toBe('pay [masked:BANK] today')
    expect(mask('BSB 062-000, Acc No. 1234567890')).toBe('BSB [masked:BANK]')
    expect(mask('062-000/123456')).toBe('[masked:BANK]')
  })

  test('Bearer and Xero tokens', () => {
    expect(mask('Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig_abc')).toBe('Authorization: [masked:TOKEN]')
    expect(mask('XERO_ACCESS_TOKEN=abc123def456')).toBe('[masked:TOKEN]')
    expect(mask('{"xero_refresh_token": "r-tok-99"}')).toBe('{"[masked:TOKEN]"}')
    expect(mask('xeroToken=zzz&next=1')).toBe('[masked:TOKEN]&next=1')
  })

  test('counts every kind', () => {
    const counts: Counts = {}
    maskText('123456782 / 51824753556 / 062-000 12345678 / 987 654 321', counts)
    expect(counts).toEqual({ TFN: 2, ABN: 1, BANK: 1 })
    expect(total(counts)).toBe(4)
  })

  test('walks structured results', () => {
    const counts: Counts = {}
    const out = maskValue({ content: [{ type: 'text', text: 'TFN 123456782' }], n: 123456782 }, counts)
    expect(out).toEqual({ content: [{ type: 'text', text: 'TFN [masked:TFN]' }], n: 123456782 })
    expect(counts).toEqual({ TFN: 1 })
  })
})

describe('masking: false positives stay', () => {
  const keep = [
    '2026-10-06', '2026-10-06T09:30:00Z', 'call 0412 345 678', 'call +61 2 9876 5432',
    '1300 123 456', '(02) 9876 5432', '0412345678', 'INV-000123', 'INV-00012345',
    'commit 1a2b3c4d5e6f', 'v1.234567890', '12345678901234', 'order #1234567',
    'Bearer tokens are short-lived', '12 345 678 901 234',
  ]
  for (const text of keep) {
    test(`leaves "${text}" alone`, () => {
      const counts: Counts = {}
      expect(maskText(text, counts)).toBe(text)
      expect(total(counts)).toBe(0)
    })
  }
})

describe('deny rules', () => {
  const bash = (command: string) => decide('Bash', { tool: 'Bash', command })

  test('Xero writes over HTTP are refused', () => {
    expect(bash('curl -X POST https://api.xero.com/api.xro/2.0/Invoices -d @inv.json')).toMatch(/Xero/)
    expect(bash('curl --request=PUT https://API.XERO.COM/x')).toMatch(/Xero/)
    expect(bash('curl -XDELETE https://api.xero.com/x/1')).toMatch(/Xero/)
    expect(bash('curl "https://api.xero.com/x?a=1&b=2" --data-raw "{}"')).toMatch(/Xero/)
    expect(bash('cat inv.json | curl --json @- https://api.xero.com/x')).toMatch(/Xero/)
    expect(bash('echo $(curl -X POST https://api.xero.com/x)')).toMatch(/Xero/)
  })

  test('Xero reads run', () => {
    expect(bash('curl -s https://api.xero.com/api.xro/2.0/Invoices -H "Accept: application/json"')).toBeNull()
    expect(bash('curl -D - https://api.xero.com/connections')).toBeNull()
    expect(bash('grep -rn "api.xero.com" src -d skip')).toBeNull()
  })

  test('Xero MCP tools: reads run, everything else is refused', () => {
    for (const t of ['mcp__xero__list_invoices', 'mcp__Xero__getContacts', 'mcp__acct-xero__search_items', 'mcp__xero__read_report']) {
      expect(decide(t, { tool: t })).toBeNull()
    }
    for (const t of ['mcp__xero__create_invoice', 'mcp__xero__update_contact', 'mcp__xero__delete_payment', 'mcp__xero__void_invoice']) {
      expect(decide(t, { tool: t })).toMatch(/not a read/)
    }
  })

  test('lodgement writes are refused', () => {
    expect(bash('npm run lodge -- --period 2026Q1')).toMatch(/lodgement/)
    expect(bash('node scripts/sbr.js submit bas.xml')).toMatch(/lodgement/)
    expect(bash('curl -X POST https://sbr.gov.au/services/lodgement')).toMatch(/lodgement/)
    expect(bash('python tools/submitLodgement.py')).toMatch(/lodgement/)
    const t = 'mcp__ato__sbr_submit_bas'
    expect(decide(t, { tool: t })).toMatch(/lodgement/)
    expect(decide('mcp__http__request', { tool: 'mcp__http__request', url: 'https://sbr.example/lodgement', method: 'POST' })).toMatch(/lodgement/)
  })

  test('lodgement reads and local work run', () => {
    expect(bash('grep -rn lodgement src/')).toBeNull()
    expect(bash('git commit -m "fix lodgement submit form"')).toBeNull()
    expect(bash('cat src/sbr/submit.ts')).toBeNull()
    expect(bash('npm test -- lodgement')).toBeNull()
    expect(decide('mcp__ato__list_lodgements', { tool: 'mcp__ato__list_lodgements' })).toBeNull()
    expect(decide('mcp__ato__get_lodgement_status', { tool: 'mcp__ato__get_lodgement_status' })).toBeNull()
    expect(decide('mcp__Linear__save_issue', { tool: 'mcp__Linear__save_issue', description: 'lodge the BAS' })).toBeNull()
  })

  test('other tools are never refused', () => {
    expect(decide('Read', { tool: 'Read', file_path: 'lodge-submit.ts' })).toBeNull()
    expect(decide('Bash', { tool: 'Bash' })).toBeNull()
  })
})

describe('scope', () => {
  test('the ATO repository and its namesakes are in scope', () => {
    expect(isAtoRemote('https://github.com/CleanExpo/ATO.git')).toBe(true)
    expect(isAtoRemote('git@github.com:CleanExpo/ATO')).toBe(true)
    expect(isAtoRemote('https://x:tok@github.com/CleanExpo/ato-ai/')).toBe(true)
    expect(repoName('git@github.com:CleanExpo/ATO.git')).toBe('ATO')
  })

  test('names that merely contain the letters are not', () => {
    for (const r of ['CleanExpo/pi-ceo-operator-mcp', 'CleanExpo/SC-Generator', 'CleanExpo/Mortgage-House-Smart-Structure-Calculator', 'CleanExpo/Pi-Dev-Ops']) {
      expect(isAtoRemote(`https://github.com/${r}.git`)).toBe(false)
    }
    expect(isAtoRemote(null)).toBe(false)
  })
})

describe('audit line', () => {
  test('holds names and counts only', () => {
    const line = auditLine({ at: '2023-11-14T22:13:20.000Z', session: 'sess-1', tool: 'Bash', decision: 'masked:2', counts: { TFN: 2 } })
    expect(JSON.parse(line)).toEqual({ at: '2023-11-14T22:13:20.000Z', session: 'sess-1', tool: 'Bash', decision: 'masked:2', counts: { TFN: 2 } })
    expect(line.endsWith('\n')).toBe(true)
    const odd = auditLine({ at: 'x', session: 'a b', tool: 'rm -rf /', decision: 'maybe', counts: {} })
    expect(JSON.parse(odd)).toMatchObject({ session: 'unknown', tool: 'unknown', decision: 'unknown' })
  })

  test('rolls past 3 MiB, named by date', () => {
    expect(needsRoll('', 'x'.repeat(10))).toBe(false)
    expect(needsRoll('x'.repeat(ROLL_BYTES), 'y')).toBe(true)
    expect(rollName(1_700_000_000_000, false)).toBe('audit-2023-11-14.jsonl')
    expect(rollName(1_700_000_000_000, true)).toBe('audit-2023-11-14T22-13-20.jsonl')
  })
})
