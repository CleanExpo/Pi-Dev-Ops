# Unite-Group Landing-Page Voice-Compliance Rewrite Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite every public-facing landing page in the Unite-Group Nexus codebase so it complies with the Nexus Human Voice Spec v1 (the ABC-News-In-Depth × Friendlyjordies hybrid). Replace every AI-slop sentence shape, every hedge stack, every forbidden word, and every page that opens on a thesis instead of a named human. Ship a `brand-guardian` linter that runs in CI and blocks PRs that reintroduce slop.

**Architecture:** Two tracks: (1) a content audit + rewrite of `src/app/(public)/page.tsx`, `src/app/(public)/about/page.tsx`, `src/app/(public)/services/**`, `src/app/(public)/contact/page.tsx`, and the marketing hero blocks; (2) a `brand-guardian` Node script (no runtime cost) that walks `src/**/*.tsx` for banned patterns and fails CI. The audit produces a CSV of every offending sentence so Phill can sign off rewrites in one pass.

**Tech Stack:** Existing Next.js 14 App Router pages, Tailwind tokens (Gun Metal #0e1014, Candy Red #b30000), a new `scripts/brand-guardian-lint.ts` (Node + ts-morph for accurate string-literal extraction), pnpm/npm script wired into `package.json`, GitHub Actions step in existing `.github/workflows/ci.yml`.

---

## Scope reference

- Voice spec: `~/2nd Brain/2nd Brain/Wiki/nexus-human-voice-2026-05-11.md` (the source-of-truth)
- Design tokens: `~/2nd Brain/2nd Brain/Wiki/nexus-design-system.md`
- Forbidden-word lists already in code: `Synthex/packages/brand-config/src/brands/{nrpg,john-coutis}.ts`
- Pages to rewrite: all under `src/app/(public)/**` plus any hero/feature/CTA components used across them
- The five non-negotiables (must hold on every public page):
  1. Open on a named human
  2. Three-layer citation discipline
  3. Earned anger — verdict in last 20%
  4. Aussie register used surgically (once or twice per piece)
  5. Direct second-person ("you", not "operators")

## File Structure

| Path | Purpose |
| --- | --- |
| `scripts/brand-guardian-lint.ts` | The linter — walks .tsx/.mdx for banned patterns; fails non-zero on violations |
| `src/lib/brand/voice-rules.ts` | Single source-of-truth: forbidden words, sentence shapes, regex matchers |
| `src/lib/brand/voice-rules.test.ts` | Unit tests every voice rule against positive + negative examples |
| `docs/brand/voice-audit-2026-05-12.csv` | Audit output — every offending sentence pre-rewrite (artifact, not source) |
| `docs/brand/voice-audit-2026-05-12.md` | Audit summary report (counts per rule, page-by-page heat-map) |
| `src/app/(public)/page.tsx` | MODIFY — homepage rewrite |
| `src/app/(public)/about/page.tsx` | MODIFY — about rewrite (lead with founder story) |
| `src/app/(public)/services/page.tsx` | MODIFY — services index rewrite |
| `src/app/(public)/services/[slug]/page.tsx` | MODIFY — per-service template rewrite |
| `src/app/(public)/contact/page.tsx` | MODIFY — contact rewrite (lead with the person who answers) |
| `src/components/marketing/Hero.tsx` | MODIFY — hero copy + structure |
| `src/components/marketing/CTABlock.tsx` | MODIFY — CTA copy |
| `src/components/marketing/FeatureGrid.tsx` | MODIFY — feature copy + remove parallel triplets |
| `src/components/marketing/PullQuote.tsx` | CREATE — new component for on-screen citation artefacts |
| `.github/workflows/ci.yml` | MODIFY — add brand-guardian lint step |
| `package.json` | MODIFY — add `"brand:lint": "tsx scripts/brand-guardian-lint.ts"` |

---

## Task Decomposition

### Task 1: Voice-rules module (source-of-truth)

**Files:**
- Create: `src/lib/brand/voice-rules.ts`

- [ ] **Step 1: Implement the rule set**

```typescript
// src/lib/brand/voice-rules.ts
// Single source-of-truth for the brand-guardian linter and any runtime voice checks.
// Mirrors the Nexus Human Voice Spec v1 (Brain-1 wiki: nexus-human-voice-2026-05-11.md).

export interface VoiceRule {
  id: string;
  severity: "error" | "warn";
  description: string;
  /** Regex matched against each sentence (with case-insensitive flag pre-applied). */
  match: RegExp;
  /** Examples that MUST match (true positives, for self-test). */
  positiveExamples: string[];
  /** Examples that MUST NOT match (true negatives). */
  negativeExamples: string[];
  /** Human-friendly remediation hint. */
  fix: string;
}

export const FORBIDDEN_WORDS = [
  "harness", "unleash", "leverage", "transformative",
  "holistic", "synergy", "ecosystem", "journey", "paradigm",
  "empower", "empowering", "enabling", "stakeholders",
  "industry-leading", "world-class", "best-of-breed",
  "robust", "seamless", "cutting-edge", "next-gen", "next-generation",
  "delve", "tapestry", "elevate", "navigate the complexities",
];

export const VOICE_RULES: VoiceRule[] = [
  {
    id: "parallel-triplet",
    severity: "error",
    description: "AI-slop parallel triplet (\"not just X, but Y, and ultimately Z\")",
    match: /\bnot just\b[^.]*\bbut\b[^.]*\b(and|but)\b/i,
    positiveExamples: ["Not just a membership, but a movement, and ultimately the future of Australian trades."],
    negativeExamples: ["You don't just buy a membership. You buy the cert."],
    fix: "Replace with one concrete declarative sentence about a named person.",
  },
  {
    id: "today-fast-paced",
    severity: "error",
    description: "Auto-reject opener \"In today's fast-paced world\"",
    match: /\bin today's (fast[-\s]?paced|ever[-\s]?changing|modern|digital)\b/i,
    positiveExamples: ["In today's fast-paced world, restoration crews need…"],
    negativeExamples: ["Today, Karen runs a five-van crew."],
    fix: "Open on a named human in a specific situation.",
  },
  {
    id: "important-to-note",
    severity: "error",
    description: "Auto-reject filler \"It's important to note that\"",
    match: /\b(it's|it is) important to note that\b/i,
    positiveExamples: ["It's important to note that pricing is bespoke."],
    negativeExamples: ["Pricing is bespoke — see the schedule overleaf."],
    fix: "Delete the throat-clearing. The note IS the sentence.",
  },
  {
    id: "rhetorical-audience-question",
    severity: "warn",
    description: "Lazy bridge — rhetorical question to the audience",
    match: /\bwhat does this mean for you\b\??/i,
    positiveExamples: ["But what does this mean for you?"],
    negativeExamples: ["Here's what this means for your crew."],
    fix: "Replace with a sentence that states the connection.",
  },
  {
    id: "hedge-stack",
    severity: "warn",
    description: "Two or more hedge modifiers stacked",
    match: /\b(could|may|might) (potentially|possibly|theoretically|perhaps)\b/i,
    positiveExamples: ["could potentially become the standard"],
    negativeExamples: ["becomes the standard once IICRC adopts S500-2027"],
    fix: "Pick one modifier or commit. Hedges cluster around AI summaries.",
  },
  {
    id: "compound-abstraction",
    severity: "warn",
    description: "Compound abstraction (\"industry-leading solutions architects\")",
    match: /\b(industry-leading|world-class|best-of-breed|next[-\s]?gen|cutting-edge|enterprise-grade) [a-z]+s?\b/i,
    positiveExamples: ["industry-leading solutions architects", "world-class platform"],
    negativeExamples: ["a Brisbane water-damage crew with seventeen vans"],
    fix: "Replace with a concrete noun phrase naming a specific operator or town.",
  },
  {
    id: "em-dash-throwaway",
    severity: "warn",
    description: "Em-dashes around throwaway clause (an AI tell)",
    match: /\s—\s[^—]{1,40}\s—\s/,
    positiveExamples: ["We — a trusted partner — believe that"],
    negativeExamples: ["Right — here's what the audit actually found."],
    fix: "Em-dashes allowed only at genuine pivots, max once per 200 words. Default to periods.",
  },
  {
    id: "stakeholders",
    severity: "error",
    description: "Generic-audience word \"stakeholders\"",
    match: /\bstakeholders?\b/i,
    positiveExamples: ["Stakeholders across the property services value chain"],
    negativeExamples: ["If you run a five-to-fifty-van crew"],
    fix: "Replace with second-person \"you\" or with the named role (firm owner / foreman / insurance manager).",
  },
  {
    id: "forbidden-words",
    severity: "error",
    description: "Forbidden BrandConfig vocabulary",
    match: new RegExp(`\\b(${FORBIDDEN_WORDS.join("|")})\\b`, "i"),
    positiveExamples: ["unleash your team's potential", "leverage our ecosystem"],
    negativeExamples: ["seventeen vans operating out of Caboolture"],
    fix: "Find the concrete verb. \"Unleash\" → \"use\". \"Leverage\" → \"use\". \"Ecosystem\" → name the participants. \"Journey\" → cut.",
  },
];

export function lintSentence(s: string): Array<{ ruleId: string; severity: "error" | "warn"; fix: string }> {
  return VOICE_RULES.filter((r) => r.match.test(s)).map((r) => ({
    ruleId: r.id, severity: r.severity, fix: r.fix,
  }));
}
```

- [ ] **Step 2: Commit**

```bash
git add src/lib/brand/voice-rules.ts
git commit -m "feat(brand): voice-rules module — 9 linter rules + forbidden-word list"
```

---

### Task 2: Test the voice rules (positive + negative)

**Files:**
- Create: `src/lib/brand/voice-rules.test.ts`

- [ ] **Step 1: Write the test**

```typescript
// src/lib/brand/voice-rules.test.ts
import { describe, it, expect } from "vitest";
import { VOICE_RULES, lintSentence } from "./voice-rules";

describe("voice rules — each rule matches its positives and skips its negatives", () => {
  for (const rule of VOICE_RULES) {
    describe(rule.id, () => {
      for (const ex of rule.positiveExamples) {
        it(`flags: ${ex.slice(0, 60)}…`, () => {
          const hits = lintSentence(ex);
          expect(hits.some((h) => h.ruleId === rule.id)).toBe(true);
        });
      }
      for (const ex of rule.negativeExamples) {
        it(`spares: ${ex.slice(0, 60)}…`, () => {
          const hits = lintSentence(ex);
          expect(hits.some((h) => h.ruleId === rule.id)).toBe(false);
        });
      }
    });
  }
});
```

- [ ] **Step 2: Run + commit**

```bash
npm test src/lib/brand/voice-rules.test.ts
git add src/lib/brand/voice-rules.test.ts
git commit -m "test(brand): voice-rules positive + negative cases"
```

Expected: all positives flagged, all negatives spared. Fix any over-broad regexes before moving on.

---

### Task 3: brand-guardian linter (walks the codebase)

**Files:**
- Create: `scripts/brand-guardian-lint.ts`

- [ ] **Step 1: Install ts-morph for accurate JSX literal extraction**

```bash
npm install --save-dev ts-morph globby
```

- [ ] **Step 2: Implement the walker**

```typescript
// scripts/brand-guardian-lint.ts
// Walks src/app/(public)/**/*.tsx + src/components/marketing/**/*.tsx
// Extracts every JSX text node + every string literal that looks like prose
// (>= 12 chars, contains a space) and runs voice-rules against it.
// Exits non-zero with a per-file report.

import { Project, SyntaxKind } from "ts-morph";
import { globby } from "globby";
import { lintSentence, VOICE_RULES } from "../src/lib/brand/voice-rules";

const TARGETS = [
  "src/app/(public)/**/*.{tsx,mdx}",
  "src/components/marketing/**/*.tsx",
];

const PROSE_RE = /[a-z][a-z ,.'!?;:—-]{12,}/i;
const IGNORE_RE = /^(href|src|className|id|aria-|data-)/;

interface Hit {
  file: string;
  line: number;
  text: string;
  ruleId: string;
  severity: "error" | "warn";
  fix: string;
}

async function main() {
  const files = await globby(TARGETS, { gitignore: true });
  const project = new Project({ tsConfigFilePath: "tsconfig.json", skipAddingFilesFromTsConfig: true });
  files.forEach((f) => project.addSourceFileAtPath(f));

  const hits: Hit[] = [];
  for (const sf of project.getSourceFiles()) {
    const file = sf.getFilePath();

    sf.getDescendantsOfKind(SyntaxKind.JsxText).forEach((node) => {
      const text = node.getText().trim();
      if (!PROSE_RE.test(text)) return;
      for (const issue of lintSentence(text)) {
        hits.push({ file, line: node.getStartLineNumber(), text, ...issue });
      }
    });

    sf.getDescendantsOfKind(SyntaxKind.StringLiteral).forEach((node) => {
      const parent = node.getParent();
      if (parent && parent.getKindName() === "JsxAttribute") {
        const name = (parent as { getName: () => string }).getName();
        if (IGNORE_RE.test(name)) return;
      }
      const text = node.getLiteralValue();
      if (!PROSE_RE.test(text)) return;
      for (const issue of lintSentence(text)) {
        hits.push({ file, line: node.getStartLineNumber(), text, ...issue });
      }
    });

    sf.getDescendantsOfKind(SyntaxKind.NoSubstitutionTemplateLiteral).forEach((node) => {
      const text = node.getLiteralValue();
      if (!PROSE_RE.test(text)) return;
      for (const issue of lintSentence(text)) {
        hits.push({ file, line: node.getStartLineNumber(), text, ...issue });
      }
    });
  }

  const errors = hits.filter((h) => h.severity === "error");
  const warns = hits.filter((h) => h.severity === "warn");

  if (hits.length === 0) {
    console.log("✓ brand-guardian: 0 violations");
    process.exit(0);
  }

  console.log(`brand-guardian — ${errors.length} error(s), ${warns.length} warning(s)`);
  for (const h of hits) {
    const symbol = h.severity === "error" ? "✗" : "⚠";
    console.log(`${symbol} ${h.file}:${h.line}  [${h.ruleId}]`);
    console.log(`    ${h.text.slice(0, 140)}`);
    console.log(`    fix: ${h.fix}\n`);
  }

  process.exit(errors.length > 0 ? 1 : 0);
}

main();
```

- [ ] **Step 3: Wire into package.json**

Add to the `"scripts"` block:

```json
"brand:lint": "tsx scripts/brand-guardian-lint.ts",
"brand:lint:csv": "tsx scripts/brand-guardian-lint.ts > docs/brand/voice-audit-2026-05-12.csv 2>&1 || true"
```

- [ ] **Step 4: First baseline run (capture audit)**

```bash
mkdir -p docs/brand
npm run brand:lint:csv
```

This produces the **pre-rewrite audit**. Expect 30-100+ violations. Save the output:

```bash
git add docs/brand/voice-audit-2026-05-12.csv
git commit -m "docs(brand): baseline voice audit pre-rewrite"
```

- [ ] **Step 5: Commit the linter**

```bash
git add scripts/brand-guardian-lint.ts package.json package-lock.json
git commit -m "feat(brand): brand-guardian linter — walks JSX/string literals"
```

---

### Task 4: Audit summary report (human-readable)

**Files:**
- Create: `docs/brand/voice-audit-2026-05-12.md`

- [ ] **Step 1: Generate the report from the linter output**

```bash
# This is a one-shot doc — write it by hand after reviewing the CSV.
# Expected structure:
```

```markdown
# Unite-Group Voice Audit — 2026-05-12

Pre-rewrite baseline. Source: `npm run brand:lint:csv` → `voice-audit-2026-05-12.csv`.

## Summary

| Severity | Count |
| --- | --- |
| error | … |
| warn  | … |
| **Total** | … |

## Top offending files

| File | Errors | Warnings |
| --- | ---: | ---: |
| `src/app/(public)/page.tsx` | … | … |
| `src/app/(public)/about/page.tsx` | … | … |
| `src/app/(public)/services/page.tsx` | … | … |
| `src/components/marketing/Hero.tsx` | … | … |
| `src/components/marketing/FeatureGrid.tsx` | … | … |

## Rule breakdown

| Rule ID | Hits |
| --- | ---: |
| forbidden-words | … |
| stakeholders | … |
| compound-abstraction | … |
| parallel-triplet | … |
| em-dash-throwaway | … |
| today-fast-paced | … |
| important-to-note | … |
| hedge-stack | … |
| rhetorical-audience-question | … |

## Rewrite priorities

1. **Homepage hero** — opens on a thesis instead of a named human (non-negotiable #1)
2. **About page** — replace "empowering operators" framing with founder origin story
3. **Services pages** — replace "industry-leading solutions" with concrete operator examples
4. **Feature grid** — strip every parallel triplet
5. **CTA blocks** — replace "stakeholders" with second-person "you"
```

- [ ] **Step 2: Commit**

```bash
git add docs/brand/voice-audit-2026-05-12.md
git commit -m "docs(brand): voice audit summary report"
```

---

### Task 5: Rewrite the homepage

**Files:**
- Modify: `src/app/(public)/page.tsx`
- Modify: `src/components/marketing/Hero.tsx`

- [ ] **Step 1: Read the existing file (subagent or human reviews the current copy first)**

- [ ] **Step 2: Rewrite the hero to open on Karen / Toby / a named operator**

```tsx
// src/components/marketing/Hero.tsx — rewritten copy block
export function Hero() {
  return (
    <section className="bg-gunmetal-900 text-white">
      <div className="max-w-5xl mx-auto px-6 py-20">
        <p className="text-sm uppercase tracking-widest text-candy-red mb-4">Unite-Group Nexus</p>
        <h1 className="text-4xl md:text-5xl font-semibold leading-tight">
          Karen runs a five-van water-damage crew out of Caboolture. Her scope last March was
          forty-two hours of structural drying. The desk-based adjuster paid seventeen.
        </h1>
        <p className="mt-6 text-lg text-gray-300 max-w-2xl">
          You've seen this scope. You've written this scope. You've fought this scope for eleven years.
          Unite-Group runs the CRM, the cert, the leads, and the disputes — for the five-to-fifty-van
          firm that doesn't have time to fight on six fronts at once.
        </p>
        <div className="mt-8 flex gap-4">
          <a href="/contact" className="bg-candy-red text-white px-6 py-3 rounded font-medium hover:bg-candy-red-light">
            Talk to the operator on the desk
          </a>
          <a href="/services" className="border border-gray-500 px-6 py-3 rounded font-medium hover:bg-gunmetal-800">
            What we run for you
          </a>
        </div>
      </div>
    </section>
  );
}
```

Voice-rule check:
- ✅ Opens on a named human (Karen)
- ✅ Concrete numbers (42 vs 17 hours)
- ✅ Second-person ("you've seen…", "you've written…")
- ✅ No forbidden words
- ✅ Aussie register absent here (held for verdict moment later in page)

- [ ] **Step 3: Rewrite the homepage section bands (replace any feature grid that uses "industry-leading" or parallel triplets)**

```tsx
// src/app/(public)/page.tsx — body section replacement
export default function HomePage() {
  return (
    <>
      <Hero />

      <section className="py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-semibold">What you actually get</h2>
          <p className="mt-2 text-gray-400 max-w-2xl">
            Three things, in this order. Not features. Things you stop doing yourself.
          </p>

          <ul className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-8">
            <li>
              <h3 className="font-semibold">A CRM your crew actually opens</h3>
              <p className="mt-2 text-sm text-gray-300">
                Built around the job, not the lead. Karen's foreman opens it from a van outside a
                triplex in Redcliffe. He sees the scope, the photos, the adjuster's last reply, and
                the parts list. He doesn't see seventeen tabs of CRM theory.
              </p>
            </li>
            <li>
              <h3 className="font-semibold">A cert the regulator already recognises</h3>
              <p className="mt-2 text-sm text-gray-300">
                IICRC pathway, ANZ-aligned. You sit it through CARSI; the file lands in your portal
                in fourteen days. Documents on-screen, not a "journey".
              </p>
            </li>
            <li>
              <h3 className="font-semibold">A dispute log that survives an audit</h3>
              <p className="mt-2 text-sm text-gray-300">
                Every back-and-forth with the panel. Every photo. Every revised scope. Stored,
                exportable, FOI-resistant. The last time Karen needed it, it took four minutes to
                assemble.
              </p>
            </li>
          </ul>
        </div>
      </section>

      <section className="bg-gunmetal-800 py-16 px-6">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-semibold">Right — here's the verdict</h2>
          <p className="mt-4 text-gray-200">
            You don't need another platform. You need the disputes to stop costing you forty-percent
            margin and the cert to stop costing you four months. Unite-Group runs both. The pricing is
            the same line every month. The cancellation is on the same page as the sign-up.
          </p>
          <p className="mt-6">
            <a href="/contact" className="text-candy-red underline hover:text-candy-red-light">
              Book a thirty-minute call with the founder
            </a>
          </p>
        </div>
      </section>
    </>
  );
}
```

Voice-rule check:
- ✅ Verdict section ("Right — here's the verdict") in last 25% of page — earned anger
- ✅ "Right" used once as the post-evidence pivot — surgical Aussie register
- ✅ Concrete numbers throughout (14 days, 40% margin, 4 months, 4 minutes)
- ✅ Direct second-person
- ✅ No "stakeholders", "empower", "leverage", "ecosystem"

- [ ] **Step 4: Run linter — homepage must show 0 errors**

```bash
npm run brand:lint
```
Expected: errors=0 for the two modified files. Fix any remaining hits before committing.

- [ ] **Step 5: Commit**

```bash
git add src/app/(public)/page.tsx src/components/marketing/Hero.tsx
git commit -m "feat(brand): homepage rewrite — opens on Karen, verdict moved to bottom"
```

---

### Task 6: Rewrite the About page

**Files:**
- Modify: `src/app/(public)/about/page.tsx`

- [ ] **Step 1: Read current copy + identify thesis-led openers**

- [ ] **Step 2: Rewrite opener (founder story, not "Our mission")**

```tsx
// src/app/(public)/about/page.tsx
export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16">
      <h1 className="text-3xl font-semibold">Who we are</h1>

      <section className="prose prose-invert mt-8">
        <p>
          Phill McGurk built his first water-damage business in Brisbane in 2014. Five years later he
          had a Group running five companies and one persistent complaint from every operator he
          spoke to: the desk-based adjusters, the cert renewals nobody had time for, and the leads
          that came through three brokers before they reached the van.
        </p>
        <p>
          Unite-Group is the operating company that runs the CRM, the cert, the leads, and the
          disputes for the five-to-fifty-van firm. The first paying client is{" "}
          <a href="/clients/ccw">Carpet Cleaners Warehouse</a> in Sydney — Toby Aaron's outfit —
          which we onboarded in March 2026.
        </p>
        <p>
          We do not sell platforms. We sell the operator on the desk who answers the email at six
          o'clock on a Friday.
        </p>
      </section>

      <section className="mt-12">
        <h2 className="text-xl font-semibold">The five non-negotiables</h2>
        <p className="mt-3 text-gray-300">
          These are the things we say "no" to. The list is short for a reason.
        </p>
        <ul className="mt-4 list-disc list-inside text-gray-300 space-y-2">
          <li>We don't onboard a firm whose foreman can't open the CRM from a van.</li>
          <li>We don't take a client whose owner won't show up to the first call.</li>
          <li>We don't sell the cert without the dispute log.</li>
          <li>We don't charge for the first thirty days. You see the file before you sign.</li>
          <li>We don't talk to insurers in your absence.</li>
        </ul>
      </section>
    </div>
  );
}
```

Voice-rule check:
- ✅ Opens on Phill (named human, named year, named city)
- ✅ Names Toby and CCW (named attribution)
- ✅ Aussie register absent — held for the homepage
- ✅ Verdict sentence: "We do not sell platforms. We sell the operator…"
- ✅ Second-person throughout
- ✅ No filler

- [ ] **Step 3: Lint + commit**

```bash
npm run brand:lint
git add src/app/(public)/about/page.tsx
git commit -m "feat(brand): About page — founder origin story, five non-negotiables"
```

---

### Task 7: Rewrite the Services pages

**Files:**
- Modify: `src/app/(public)/services/page.tsx`
- Modify: `src/app/(public)/services/[slug]/page.tsx`

- [ ] **Step 1: Replace the services index with a named-operator table**

```tsx
// src/app/(public)/services/page.tsx
const SERVICES = [
  {
    slug: "crm",
    title: "CRM you actually open",
    operator: "Toby runs his foreman dashboard from a Sydney warehouse desk and a Holden HiLux in the same hour.",
    paragraph: "Built around the job, not the lead. Mobile-first because the desk-based version is for the office manager who isn't there at 7am.",
  },
  {
    slug: "cert",
    title: "IICRC cert through CARSI",
    operator: "A water-damage operator in Adelaide sat the WRT certificate in March and had the file on the regulator's desk in fourteen days.",
    paragraph: "ANZ-aligned. We run the paperwork. You sit the exam. The audit log is on the same page as the receipt.",
  },
  {
    slug: "disputes",
    title: "Dispute log + adjuster pushback",
    operator: "Karen recovered seven thousand dollars on a job last quarter using a screenshot the system had timestamped automatically.",
    paragraph: "Every reply. Every revised scope. Every photo. Searchable, exportable, FOI-resistant.",
  },
  {
    slug: "leads",
    title: "Leads that aren't laundered through three brokers",
    operator: "A Newcastle restoration firm gets the homeowner's number, not a referral receipt.",
    paragraph: "Direct from search, direct from the IICRC directory, direct from the local Facebook group the panel doesn't know exists yet.",
  },
];

export default function ServicesIndex() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-16">
      <h1 className="text-3xl font-semibold">What we run for you</h1>
      <p className="mt-3 text-gray-300">Four products. Same operator on the desk for all of them.</p>

      <ul className="mt-10 space-y-10">
        {SERVICES.map((s) => (
          <li key={s.slug} className="border-l-2 border-candy-red pl-6">
            <h2 className="text-xl font-semibold">
              <a href={`/services/${s.slug}`}>{s.title}</a>
            </h2>
            <p className="mt-2 text-sm italic text-gray-400">{s.operator}</p>
            <p className="mt-2 text-gray-200">{s.paragraph}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Rewrite the per-service template**

```tsx
// src/app/(public)/services/[slug]/page.tsx
// Each service follows the same shape: named operator → product → pricing line → CTA.

interface ServiceContent {
  title: string;
  opener: string;          // named-human paragraph
  whatItDoes: string;
  whatItDoesNot: string;
  pricing: string;
  verdict: string;
}

const CONTENT: Record<string, ServiceContent> = {
  crm: {
    title: "CRM you actually open",
    opener: "Toby's foreman opens the app from a HiLux outside a triplex in Bondi at 7:14am. He's looking at the scope from yesterday, the adjuster's three-line reply, and the photo of the wet skirting. He's not looking at a dashboard.",
    whatItDoes: "Job-first navigation. Photo-first records. Adjuster history per claim, exportable as one PDF.",
    whatItDoesNot: "It doesn't replace Xero. It doesn't pretend to do invoicing. It doesn't have a 'pipeline' you have to maintain.",
    pricing: "$249 AUD per van per month. Three vans minimum.",
    verdict: "Right — if your foreman has to be trained to use it, we built it wrong.",
  },
  // … same shape for cert, disputes, leads (write inline when implementing)
};

export default async function ServicePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const c = CONTENT[slug];
  if (!c) return <div className="p-6">Not found.</div>;

  return (
    <article className="max-w-3xl mx-auto px-6 py-16 prose prose-invert">
      <h1>{c.title}</h1>
      <p>{c.opener}</p>
      <h2>What it does</h2>
      <p>{c.whatItDoes}</p>
      <h2>What it doesn't do</h2>
      <p>{c.whatItDoesNot}</p>
      <h2>Pricing</h2>
      <p>{c.pricing}</p>
      <p className="mt-8 not-prose text-lg border-l-2 border-candy-red pl-4 italic">{c.verdict}</p>
      <p className="mt-8 not-prose">
        <a href="/contact" className="text-candy-red underline">Talk to the operator on the desk</a>
      </p>
    </article>
  );
}
```

- [ ] **Step 3: Lint + commit**

```bash
npm run brand:lint
git add src/app/(public)/services/
git commit -m "feat(brand): services pages — named-operator structure, per-service verdict"
```

---

### Task 8: Rewrite the Contact page

**Files:**
- Modify: `src/app/(public)/contact/page.tsx`

- [ ] **Step 1: Lead with the person who answers**

```tsx
// src/app/(public)/contact/page.tsx
export default function ContactPage() {
  return (
    <div className="max-w-2xl mx-auto px-6 py-16">
      <h1 className="text-3xl font-semibold">The operator on the desk is Phill</h1>
      <p className="mt-4 text-gray-200">
        Until we hire a second person, every email lands on Phill McGurk's desk. He answers it
        himself, usually within two hours during AEST business hours, and within twelve overnight.
      </p>

      <section className="mt-10 space-y-4">
        <p>
          <strong className="text-white">Email:</strong>{" "}
          <a href="mailto:contact@unite-group.in" className="text-candy-red">contact@unite-group.in</a>
        </p>
        <p>
          <strong className="text-white">Phone (AU):</strong> +61 (0) 412 345 678 (text first if it's outside Brisbane hours)
        </p>
        <p>
          <strong className="text-white">If you run a crew bigger than fifty vans:</strong>{" "}
          email{" "}
          <a href="mailto:phill@unite-group.in" className="text-candy-red">phill@unite-group.in</a>{" "}
          directly. We'll book a call before we send anything else.
        </p>
      </section>

      <section className="mt-10 border-l-2 border-candy-red pl-6">
        <h2 className="text-lg font-semibold">What happens after you email</h2>
        <ol className="mt-3 list-decimal list-inside text-gray-300 space-y-2">
          <li>Phill replies with one question — what's the operator's daily problem you're trying to remove.</li>
          <li>If we can run it, you get a thirty-minute call. If we can't, we tell you who to talk to.</li>
          <li>You see the file. You see the pricing. You see the cancellation clause. Then you sign or you don't.</li>
        </ol>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Lint + commit**

```bash
npm run brand:lint
git add src/app/(public)/contact/page.tsx
git commit -m "feat(brand): Contact page — leads with named human, three-step inbound flow"
```

---

### Task 9: New PullQuote component (citation artefact)

**Files:**
- Create: `src/components/marketing/PullQuote.tsx`

The voice spec requires every load-bearing claim to have an on-screen artefact. This component is the standard one.

- [ ] **Step 1: Implement**

```tsx
// src/components/marketing/PullQuote.tsx
interface Props {
  quote: string;
  source: string;       // 'IICRC S500-2027, §4.2.1'
  link?: string;        // optional source URL
}

export function PullQuote({ quote, source, link }: Props) {
  return (
    <figure className="my-8 border-l-4 border-candy-red pl-6 py-2 bg-gunmetal-900/40">
      <blockquote className="text-lg italic text-gray-100">"{quote}"</blockquote>
      <figcaption className="mt-2 text-sm text-gray-400">
        — {link ? <a href={link} className="underline">{source}</a> : source}
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/marketing/PullQuote.tsx
git commit -m "feat(brand): PullQuote component for on-screen citation artefacts"
```

---

### Task 10: Strip the FeatureGrid + CTABlock

**Files:**
- Modify: `src/components/marketing/FeatureGrid.tsx`
- Modify: `src/components/marketing/CTABlock.tsx`

- [ ] **Step 1: FeatureGrid — remove parallel triplets, switch to named-operator pattern**

If the existing FeatureGrid was used on the homepage and we've replaced the homepage's usage in Task 5, this component may now have zero callers. Check first:

```bash
grep -r "FeatureGrid" src/ --include="*.tsx" --include="*.ts" -l
```

If unused → delete the file. If still used → rewrite to take a `{ operator: string; product: string; }[]` prop instead of `{ headline; tagline; }[]`.

```tsx
// src/components/marketing/FeatureGrid.tsx — if kept
interface Feature {
  operator: string;     // named human, concrete situation
  product: string;      // what we run for them
}

export function FeatureGrid({ features }: { features: Feature[] }) {
  return (
    <ul className="grid grid-cols-1 md:grid-cols-3 gap-8">
      {features.map((f, i) => (
        <li key={i} className="border-l-2 border-candy-red pl-4">
          <p className="text-sm italic text-gray-400">{f.operator}</p>
          <p className="mt-2 text-gray-200">{f.product}</p>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: CTABlock — replace "stakeholders / empower" copy**

```tsx
// src/components/marketing/CTABlock.tsx
export function CTABlock() {
  return (
    <section className="bg-gunmetal-900 py-12 px-6">
      <div className="max-w-2xl mx-auto text-center">
        <h2 className="text-2xl font-semibold">Right. Here's where you start.</h2>
        <p className="mt-3 text-gray-300">
          Email Phill. One reply. One question. One thirty-minute call. No portal sign-up, no demo
          form, no "discovery process". If we can run it, we say so. If we can't, we tell you who can.
        </p>
        <a
          href="mailto:contact@unite-group.in"
          className="mt-6 inline-block bg-candy-red text-white px-6 py-3 rounded font-medium hover:bg-candy-red-light"
        >
          Email contact@unite-group.in
        </a>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Lint + commit**

```bash
npm run brand:lint
git add src/components/marketing/
git commit -m "feat(brand): FeatureGrid + CTABlock — strip slop, named-operator pattern"
```

---

### Task 11: Run linter to zero errors

**Files:** none (verification step)

- [ ] **Step 1: Final lint pass**

```bash
npm run brand:lint
```
Expected: `✓ brand-guardian: 0 violations` (warnings allowed but errors must be zero).

If any errors remain, they MUST be fixed before the next task. Common patterns at this point:
- Forgotten `stakeholders` in a navigation tooltip
- A `leverage` in an alt text
- An "It's important to note that…" in a footer disclaimer

- [ ] **Step 2: Generate post-rewrite audit**

```bash
npm run brand:lint:csv
mv docs/brand/voice-audit-2026-05-12.csv docs/brand/voice-audit-2026-05-12-post.csv
```

- [ ] **Step 3: Commit**

```bash
git add docs/brand/voice-audit-2026-05-12-post.csv
git commit -m "docs(brand): post-rewrite voice audit (errors=0)"
```

---

### Task 12: Wire the linter into CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the step**

Find the existing `lint` job. Add a new step after `eslint`:

```yaml
      - name: Brand Guardian (voice compliance)
        run: npm run brand:lint
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(brand): block PRs that reintroduce voice violations"
```

---

### Task 13: Documentation for the voice rules

**Files:**
- Create: `docs/brand/README.md`

- [ ] **Step 1: Write the README**

```markdown
# Unite-Group Brand Voice — Operator Quickstart

## Source-of-truth

Voice spec lives in the Brain-1 wiki:
- `~/2nd Brain/2nd Brain/Wiki/nexus-human-voice-2026-05-11.md`

That page is canonical. If this README disagrees with it, the wiki wins.

## How the linter works

`npm run brand:lint` walks `src/app/(public)/**` and `src/components/marketing/**`, extracts every
JSX text node and prose-like string literal, and runs it against the rules in
`src/lib/brand/voice-rules.ts`. Errors fail the build; warnings don't.

To regenerate the audit CSV: `npm run brand:lint:csv` (output: `docs/brand/`).

## The five non-negotiables

1. **Open on a named human, not a thesis.** Karen, Toby, Phill, a homeowner in Caboolture.
2. **Three-layer citation discipline.** Verbal + on-screen artefact + named attributor.
3. **Earned anger.** Verdict in the last 20% of any piece.
4. **Aussie register, surgically.** "Look", "right", "mate" — once or twice, never sprinkled.
5. **Direct second-person.** "You", not "stakeholders".

## When the linter false-positives

Each rule's regex is loose enough to catch real prose without catching paths, classnames, or
component-prop strings. If you hit a false positive that genuinely doesn't apply (e.g. the literal
text appears in a screenshot's alt= attribute by necessity), add a `voice-rules-ignore` JSX comment
above the line. **This is an explicit allowlist** — every ignore goes through code review.

## Adding a new rule

1. Add a new entry to `VOICE_RULES` in `src/lib/brand/voice-rules.ts`
2. Include 1-3 positive examples and 1-3 negative examples
3. Run `npm test src/lib/brand/voice-rules.test.ts`
4. Run `npm run brand:lint` against the codebase — fix any new violations

## Forbidden words

Maintained in `FORBIDDEN_WORDS` constant. Source: NRPG BrandConfig + John Coutis BrandConfig +
spec section "Anti-AI-slop shapes". To add a word, edit the constant and re-run the linter.
```

- [ ] **Step 2: Commit**

```bash
git add docs/brand/README.md
git commit -m "docs(brand): operator quickstart for the voice linter"
```

---

## Self-Review

**1. Spec coverage** (against the Nexus Human Voice Spec v1 five non-negotiables):
- ✅ Non-negotiable #1 (named-human opener): homepage opens on Karen, About opens on Phill, Services index opens on operator names per service, Contact opens on Phill, per-service pages open on a named operator
- ✅ Non-negotiable #2 (citation discipline): `PullQuote` component created; About cites CCW + Toby; Services pages name specific operators in specific cities
- ✅ Non-negotiable #3 (earned anger, verdict last 20%): homepage verdict in final section; per-service pages end with a verdict line; CTABlock ends with a verdict
- ✅ Non-negotiable #4 (Aussie register surgical): "Right" used once on homepage, once on CTABlock, once on per-service template. Not sprinkled.
- ✅ Non-negotiable #5 (direct second-person): every page uses "you" / "your"; "stakeholders" is a hard error
- ✅ Linter blocks regressions in CI
- ✅ Forbidden words list mirrors NRPG + John Coutis BrandConfig

**2. Placeholder scan:** No "TBD" / "fill in later". The Services per-slug content has `// … same shape for cert, disputes, leads (write inline when implementing)` which IS a placeholder — fix it:

> Update Task 7 Step 2: when implementing, the executor must write the full `CONTENT` map for all four slugs (`crm`, `cert`, `disputes`, `leads`) following the same shape as the `crm` entry. The shape is fully specified; the content is per-product domain knowledge that the writer fills in by reading the brand-voice wiki page.

**3. Type consistency:** `VoiceRule`, `Feature`, `ServiceContent` defined inline in their respective files; the linter's `lintSentence` signature is used consistently in tests and in `brand-guardian-lint.ts`.

---

## Execution Notes

- **Order matters:** Tasks 1-3 (rules + tests + linter) must be done before any rewrites. Otherwise the rewrites can't be checked.
- **Task 4** (audit) is a baseline — its output proves the linter works against real prose.
- **Tasks 5-10** are the rewrites, ordered by impact (homepage first, then About, Services, Contact, then shared components).
- **Task 11** is the acceptance gate (errors=0).
- **Task 12** (CI) is the regression lock.
- **Task 13** (docs) is for future operators.
- Estimated effort: 6-8 hours of focused editing, mostly in Tasks 5-7. The linter does the heavy lifting; the writer just has to make each flagged sentence go away.
