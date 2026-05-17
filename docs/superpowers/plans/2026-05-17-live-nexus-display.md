# Live Nexus Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project 3 of 3 — a Vercel-hosted SPA at `live.unite-group.in` that does live AssemblyAI streaming transcription + Anthropic Haiku 4.5 synthesis sidebar, saves the final meeting markdown to a Google Drive folder, with Unite-Group Nexus branding.

**Architecture:** New `live-nexus/` directory inside the Pi-Dev-Ops monorepo (NOT a separate repo — monorepo subdir reduces ceremony; can extract later if it becomes a standalone product). Next.js 16 + React 19 + TypeScript strict + Tailwind. Three Edge Runtime API routes broker AssemblyAI / Anthropic / Google Drive keys. Source of truth: `docs/superpowers/specs/2026-05-17-live-nexus-display-design.md`.

**Tech Stack:** Next.js 16, React 19, TypeScript strict, Tailwind 4, shadcn/ui primitives, AssemblyAI JS SDK, `@anthropic-ai/sdk`, `googleapis` (Drive auth via service account), Vitest, Playwright. Vercel Edge Runtime for API routes.

**Plan deviations from spec:**
- Monorepo subdir (`Pi-Dev-Ops/live-nexus/`) instead of separate GitHub repo. The spec said "new repo or monorepo subdir" — picking subdir to reduce one-time setup steps.
- `@unite-group/brand-config` is workspace-linked from `Pi-Dev-Ops/packages/brand-config` rather than published to npm.

---

## File map

| File | Status | Purpose |
|---|---|---|
| `live-nexus/package.json` | NEW | Next.js 16, React 19, deps |
| `live-nexus/tsconfig.json` | NEW | TS strict |
| `live-nexus/next.config.js` | NEW | Edge runtime config |
| `live-nexus/tailwind.config.ts` | NEW | Brand tokens |
| `live-nexus/vitest.config.ts` | NEW | Vitest setup |
| `live-nexus/playwright.config.ts` | NEW | E2E setup |
| `live-nexus/app/layout.tsx` | NEW | Brand chrome + dark mode |
| `live-nexus/app/page.tsx` | NEW | Landing + pre-flight |
| `live-nexus/app/m/[id]/page.tsx` | NEW | Active meeting SPA |
| `live-nexus/app/globals.css` | NEW | Tailwind + brand tokens |
| `live-nexus/app/api/session/route.ts` | NEW | AssemblyAI temp token mint |
| `live-nexus/app/api/synthesize/route.ts` | NEW | Anthropic Haiku synthesis |
| `live-nexus/app/api/save/route.ts` | NEW | Drive markdown save |
| `live-nexus/lib/slug.ts` | NEW | Filename slug helper |
| `live-nexus/lib/brand-tokens.ts` | NEW | Color/font constants |
| `live-nexus/lib/markdown-composer.ts` | NEW | Meeting state → markdown |
| `live-nexus/lib/drive-client.ts` | NEW | Service-account Drive helper |
| `live-nexus/lib/anthropic-client.ts` | NEW | Anthropic Messages helper (edge) |
| `live-nexus/lib/assemblyai-client.ts` | NEW | Browser WS wrapper + reconnect |
| `live-nexus/lib/synthesis-poller.ts` | NEW | 30s polling loop |
| `live-nexus/lib/indexeddb-session.ts` | NEW | Browser crash-recovery store |
| `live-nexus/components/MeetingHeader.tsx` | NEW | Brand banner + LIVE dot + timer |
| `live-nexus/components/TranscriptStream.tsx` | NEW | Left 60% transcript panel |
| `live-nexus/components/SynthesisSidebar.tsx` | NEW | Right 40% Topics + Actions |
| `live-nexus/components/ConnectionStatus.tsx` | NEW | Reconnect banner |
| `live-nexus/components/PreflightCheck.tsx` | NEW | Mic/network/browser detection |
| `live-nexus/tests/**/*.test.{ts,tsx}` | NEW | Vitest unit suite |
| `live-nexus/e2e/start-end-meeting.spec.ts` | NEW | Playwright E2E |
| `live-nexus/tests/live-meeting.live.test.ts` | NEW | Opt-in real-API test |
| `live-nexus/README.md` | NEW | Setup + deploy docs |
| `live-nexus/.gitignore` | NEW | node_modules, .next, .env.local |

---

## Task 0: Provision external accounts + DNS

**Files:** none (manual user steps, no code)

- [ ] **Step 1: AssemblyAI account**

Sign up at https://www.assemblyai.com/. Add at least $20 credit (covers ~30 hours of streaming). Copy the API key from dashboard → API Keys.

**Save to:** `~/.hermes/.env` line: `ASSEMBLYAI_API_KEY=<value>`. Also paste into the Vercel project env (Task 19).

- [ ] **Step 2: GCP service account for Drive**

Open https://console.cloud.google.com/. Create a new project `live-nexus` if none exists. Enable Google Drive API (APIs & Services → Library → search "Google Drive API" → Enable). Then IAM & Admin → Service Accounts → Create Service Account named `live-nexus-saver`. Generate a JSON key — DOWNLOAD IT. Note the service-account email (`live-nexus-saver@<project-id>.iam.gserviceaccount.com`).

**Save the JSON key contents** somewhere safe; you'll paste it into the Vercel env as `DRIVE_SERVICE_ACCOUNT_JSON` (Task 19).

- [ ] **Step 3: Create Drive folder, share with service account**

Open https://drive.google.com/. Create the path `My Drive/Brain/Live-Nexus/` (two-level: parent "Brain", child "Live-Nexus"). Right-click `Live-Nexus` → Share → paste the service-account email from Step 2, set permission to **Editor**, uncheck "Notify people". Click Share.

Copy the folder ID from the URL. URL shape: `https://drive.google.com/drive/folders/<FOLDER_ID>`.

**Save:** the folder ID for the Vercel env as `DRIVE_FOLDER_ID` (Task 19).

- [ ] **Step 4: Reserve the subdomain (DNS will land in Task 21)**

No action yet — just confirm `unite-group.in` is in a DNS provider you control (Cloudflare, Namecheap, etc.). The subdomain `live.unite-group.in` will be pointed at Vercel in Task 21.

- [ ] **Step 5: No commit. Move on.**

---

## Task 1: Scaffold the Next.js project

**Files:**
- Create: `live-nexus/` directory with all skeleton files

- [ ] **Step 1: Generate the Next.js skeleton**

Run from the Pi-Dev-Ops root:
```bash
cd ~/Pi-CEO/Pi-Dev-Ops
npx create-next-app@latest live-nexus --typescript --tailwind --app --no-src-dir --no-eslint --turbopack --import-alias "@/*" --use-pnpm
```

Answer prompts: yes to all defaults. The flags above auto-configure most of them.

Expected: `live-nexus/` directory created with package.json, app/, components/, etc.

- [ ] **Step 2: Verify dev server starts**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus
pnpm dev
```

Expected: server on http://localhost:3000 shows the Next.js welcome page. Kill it with Ctrl+C.

- [ ] **Step 3: Install runtime deps**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus
pnpm add assemblyai @anthropic-ai/sdk googleapis
pnpm add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @types/node @playwright/test
```

- [ ] **Step 4: Add scripts to package.json**

Open `live-nexus/package.json` and ensure the `scripts` block contains:
```json
{
  "scripts": {
    "dev": "next dev --turbopack",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "vitest run",
    "test:watch": "vitest",
    "e2e": "playwright test"
  }
}
```

- [ ] **Step 5: Commit the scaffold**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/package.json live-nexus/tsconfig.json live-nexus/next.config.* live-nexus/tailwind.config.* live-nexus/postcss.config.* live-nexus/app live-nexus/public live-nexus/.gitignore live-nexus/README.md live-nexus/pnpm-lock.yaml
git commit -m "feat(live-nexus): scaffold Next.js project with deps (Task 1)"
```

Note: `node_modules/` should be gitignored by the scaffold. Verify with `git status` after the commit — no `node_modules` should appear.

---

## Task 2: Configure Vitest + create `vitest.config.ts`

**Files:**
- Create: `live-nexus/vitest.config.ts`
- Create: `live-nexus/tests/setup.ts`

- [ ] **Step 1: Create Vitest config**

`live-nexus/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
```

- [ ] **Step 2: Create setup file**

`live-nexus/tests/setup.ts`:
```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 3: Smoke-test that Vitest runs**

Create `live-nexus/lib/__tests__/smoke.test.ts`:
```typescript
import { describe, it, expect } from "vitest";

describe("smoke", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

Run:
```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm test
```
Expected: `1 passed`.

- [ ] **Step 4: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/vitest.config.ts live-nexus/tests/setup.ts live-nexus/lib/__tests__/smoke.test.ts
git commit -m "feat(live-nexus): Vitest config + smoke test (Task 2)"
```

---

## Task 3: `lib/slug.ts` (TDD)

**Files:**
- Create: `live-nexus/lib/slug.ts`
- Create: `live-nexus/lib/__tests__/slug.test.ts`

- [ ] **Step 1: Write failing tests**

`live-nexus/lib/__tests__/slug.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { slugify } from "../slug";

describe("slugify", () => {
  it("converts plain title to slug", () => {
    expect(slugify("Acme Q2 Pricing")).toBe("acme-q2-pricing");
  });

  it("strips punctuation", () => {
    expect(slugify("Acme Q2 Pricing!?")).toBe("acme-q2-pricing");
  });

  it("collapses consecutive dashes", () => {
    expect(slugify("foo --- bar")).toBe("foo-bar");
  });

  it("trims leading/trailing dashes", () => {
    expect(slugify("—foo—")).toBe("foo");
  });

  it("ascii-folds unicode", () => {
    expect(slugify("Café Sync")).toBe("cafe-sync");
  });

  it("returns 'meeting' for empty input", () => {
    expect(slugify("")).toBe("meeting");
    expect(slugify("   ")).toBe("meeting");
  });

  it("caps length at 60 chars", () => {
    const result = slugify("a".repeat(200));
    expect(result.length).toBeLessThanOrEqual(60);
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test slug
```
Expected: failure with `Cannot find module '../slug'`.

- [ ] **Step 3: Implement**

`live-nexus/lib/slug.ts`:
```typescript
/** Convert a free-text title into a filename-safe slug. */
export function slugify(name: string): string {
  if (!name || !name.trim()) return "meeting";
  const ascii = name.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  const slug = ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (slug || "meeting").slice(0, 60).replace(/-+$/, "");
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test slug
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/slug.ts live-nexus/lib/__tests__/slug.test.ts
git commit -m "feat(live-nexus): slug helper (Task 3)"
```

---

## Task 4: `lib/brand-tokens.ts`

**Files:**
- Create: `live-nexus/lib/brand-tokens.ts`

- [ ] **Step 1: Create token export**

`live-nexus/lib/brand-tokens.ts`:
```typescript
/** Unite-Group Nexus brand tokens. Duplicated here from
 * Pi-Dev-Ops/packages/brand-config until that package is workspace-linkable.
 * TODO: replace with `import { UNITE_GROUP } from "@unite-group/brand-config"`. */

export const BRAND = {
  name: "Unite Group Nexus",
  colors: {
    background: "#0e1014",        // Gun Metal
    surface: "#15181f",
    hairline: "#2a2d35",
    textPrimary: "#f4ecd8",       // warm cream
    textMuted: "#8c8a85",
    accent: "#b30000",            // Candy Red
    accentMuted: "#7a0000",
  },
  fonts: {
    body: 'Inter, -apple-system, system-ui, sans-serif',
    brand: 'Charter, "Iowan Old Style", Georgia, serif',
    mono: '"SF Mono", Menlo, Consolas, monospace',
  },
} as const;
```

- [ ] **Step 2: No tests (constants); just verify TS compiles**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/brand-tokens.ts
git commit -m "feat(live-nexus): brand tokens (Task 4)"
```

---

## Task 5: `lib/markdown-composer.ts` (TDD)

**Files:**
- Create: `live-nexus/lib/markdown-composer.ts`
- Create: `live-nexus/lib/__tests__/markdown-composer.test.ts`

- [ ] **Step 1: Write failing tests**

`live-nexus/lib/__tests__/markdown-composer.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { composeMeetingMarkdown, type MeetingState } from "../markdown-composer";

const baseState: MeetingState = {
  meetingId: "abc-123",
  title: "Acme Q2 Pricing",
  startedAt: "2026-05-17T14:32:00+10:00",
  endedAt: "2026-05-17T15:31:42+10:00",
  brand: "unite-group",
  transcript: [
    { timestamp: "14:28", speaker: "A", text: "we've got the new pricing tiers..." },
    { timestamp: "14:30", speaker: "B", text: "what about the inventory sync?" },
  ],
  topics: ["Q2 pricing tiers", "Inventory sync"],
  actions: [
    { title: "Send pricing proposal", description: "by Friday", owner: "Phill", priority: 2 },
  ],
};

describe("composeMeetingMarkdown", () => {
  it("starts with frontmatter delimiter", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md.startsWith("---\n")).toBe(true);
  });

  it("includes meeting_id in frontmatter", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("meeting_id: abc-123");
  });

  it("includes duration_human", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("duration_human: 59m42s");
  });

  it("renders title as H1", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("# Acme Q2 Pricing — 2026-05-17");
  });

  it("renders Topics section", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("## Topics Discussed");
    expect(md).toContain("- Q2 pricing tiers");
    expect(md).toContain("- Inventory sync");
  });

  it("renders Action Items section with owner", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("## Action Items");
    expect(md).toContain("- [ ] Send pricing proposal — by Friday — Phill");
  });

  it("renders Transcript section with timestamps", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("## Transcript");
    expect(md).toContain("[14:28] Speaker A: we've got the new pricing tiers...");
  });

  it("handles empty topics + actions gracefully", () => {
    const md = composeMeetingMarkdown({ ...baseState, topics: [], actions: [] });
    expect(md).toContain("## Topics Discussed");
    expect(md).toContain("_(none)_");
  });

  it("uses 'Meeting' title fallback when title is empty", () => {
    const md = composeMeetingMarkdown({ ...baseState, title: "" });
    expect(md).toContain("# Meeting — 2026-05-17");
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test markdown-composer
```
Expected: failure on import.

- [ ] **Step 3: Implement**

`live-nexus/lib/markdown-composer.ts`:
```typescript
export interface TranscriptLine {
  timestamp: string;     // "14:28"
  speaker: string;       // "A" / "B" / "?"
  text: string;
}

export interface Action {
  title: string;
  description: string;
  owner?: string;
  priority: number;      // 0..4 Linear scale
}

export interface MeetingState {
  meetingId: string;
  title: string;
  startedAt: string;     // ISO
  endedAt: string;       // ISO
  brand: string;
  transcript: TranscriptLine[];
  topics: string[];
  actions: Action[];
}

function formatDurationHuman(startISO: string, endISO: string): string {
  const ms = new Date(endISO).getTime() - new Date(startISO).getTime();
  const totalS = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(totalS / 3600);
  const m = Math.floor((totalS % 3600) / 60);
  const s = totalS % 60;
  if (h) return `${h}h${String(m).padStart(2, "0")}m${String(s).padStart(2, "0")}s`;
  if (m) return `${m}m${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

function dateOnly(iso: string): string {
  return iso.slice(0, 10);
}

export function composeMeetingMarkdown(state: MeetingState): string {
  const title = state.title.trim() || "Meeting";
  const dateStr = dateOnly(state.startedAt);

  const fm = [
    "---",
    "type: live-meeting",
    `meeting_id: ${state.meetingId}`,
    `started_at: ${state.startedAt}`,
    `ended_at: ${state.endedAt}`,
    `duration_human: ${formatDurationHuman(state.startedAt, state.endedAt)}`,
    "source: live-nexus",
    `brand: ${state.brand}`,
    "---",
  ].join("\n");

  const heading = `# ${title} — ${dateStr}`;

  const topicsSection =
    "## Topics Discussed\n" +
    (state.topics.length ? state.topics.map((t) => `- ${t}`).join("\n") : "_(none)_");

  const actionsSection =
    "## Action Items\n" +
    (state.actions.length
      ? state.actions
          .map((a) => {
            const parts = [a.title];
            if (a.description) parts.push(a.description);
            if (a.owner) parts.push(a.owner);
            return `- [ ] ${parts.join(" — ")}`;
          })
          .join("\n")
      : "_(none)_");

  const transcriptSection =
    "## Transcript\n\n" +
    state.transcript
      .map((l) => `[${l.timestamp}] Speaker ${l.speaker}: ${l.text}`)
      .join("\n");

  return [fm, "", heading, "", topicsSection, "", actionsSection, "", transcriptSection, ""].join("\n");
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test markdown-composer
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/markdown-composer.ts live-nexus/lib/__tests__/markdown-composer.test.ts
git commit -m "feat(live-nexus): markdown composer for saved meetings (Task 5)"
```

---

## Task 6: `/api/session` edge route (TDD)

**Files:**
- Create: `live-nexus/app/api/session/route.ts`
- Create: `live-nexus/app/api/session/__tests__/route.test.ts`

- [ ] **Step 1: Write failing tests**

`live-nexus/app/api/session/__tests__/route.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";

describe("/api/session", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("returns 500 when ASSEMBLYAI_API_KEY missing", async () => {
    delete process.env.ASSEMBLYAI_API_KEY;
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST" }));
    expect(res.status).toBe(500);
  });

  it("calls AssemblyAI token endpoint with correct headers", async () => {
    process.env.ASSEMBLYAI_API_KEY = "fake_key_123";
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ token: "tmp_abc" }), { status: 200 })
    );
    vi.resetModules();
    const { POST } = await import("../route");
    await POST(new Request("http://x", { method: "POST" }));

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "https://api.assemblyai.com/v2/realtime/token",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "fake_key_123" }),
      })
    );
  });

  it("never leaks the real key in response body", async () => {
    process.env.ASSEMBLYAI_API_KEY = "fake_key_super_secret";
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ token: "tmp_abc" }), { status: 200 })
    );
    vi.resetModules();
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST" }));
    const text = await res.text();
    expect(text).not.toContain("fake_key_super_secret");
    expect(text).toContain("tmp_abc");
  });

  it("returns ws_url and expires_at alongside token", async () => {
    process.env.ASSEMBLYAI_API_KEY = "k";
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ token: "tmp_abc" }), { status: 200 })
    );
    vi.resetModules();
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST" }));
    const body = await res.json();
    expect(body.token).toBe("tmp_abc");
    expect(body.ws_url).toBe("wss://api.assemblyai.com/v2/realtime/ws");
    expect(typeof body.expires_at).toBe("number");
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test session
```
Expected: failure (route doesn't exist).

- [ ] **Step 3: Implement**

`live-nexus/app/api/session/route.ts`:
```typescript
export const runtime = "edge";

const ASSEMBLYAI_TOKEN_URL = "https://api.assemblyai.com/v2/realtime/token";
const ASSEMBLYAI_WS_URL = "wss://api.assemblyai.com/v2/realtime/ws";
const TOKEN_EXPIRY_SECONDS = 3600;

export async function POST(_req: Request): Promise<Response> {
  const apiKey = process.env.ASSEMBLYAI_API_KEY;
  if (!apiKey) {
    return Response.json(
      { error: "ASSEMBLYAI_API_KEY not configured" },
      { status: 500 }
    );
  }

  try {
    const upstream = await fetch(ASSEMBLYAI_TOKEN_URL, {
      method: "POST",
      headers: {
        Authorization: apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expires_in: TOKEN_EXPIRY_SECONDS }),
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      console.error("[api/session] AssemblyAI rejected:", upstream.status, text);
      return Response.json({ error: "Upstream token mint failed" }, { status: 502 });
    }

    const data = (await upstream.json()) as { token: string };
    return Response.json({
      token: data.token,
      ws_url: ASSEMBLYAI_WS_URL,
      expires_at: Date.now() + TOKEN_EXPIRY_SECONDS * 1000,
    });
  } catch (e) {
    console.error("[api/session] transport error:", e);
    return Response.json({ error: "Upstream unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test session
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/app/api/session/route.ts live-nexus/app/api/session/__tests__/route.test.ts
git commit -m "feat(live-nexus): /api/session AssemblyAI token broker (Task 6)"
```

---

## Task 7: `/api/synthesize` edge route (TDD)

**Files:**
- Create: `live-nexus/app/api/synthesize/route.ts`
- Create: `live-nexus/app/api/synthesize/__tests__/route.test.ts`

- [ ] **Step 1: Write failing tests**

`live-nexus/app/api/synthesize/__tests__/route.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";

function anthropicToolUseResponse(topics: string[], actions: Array<{title:string; description:string; priority:number}>) {
  return {
    id: "msg_1",
    type: "message",
    role: "assistant",
    content: [
      {
        type: "tool_use",
        id: "toolu_1",
        name: "update_synthesis",
        input: { topics, actions },
      },
    ],
    stop_reason: "tool_use",
  };
}

describe("/api/synthesize", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn());
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  });

  it("returns 500 when ANTHROPIC_API_KEY missing", async () => {
    delete process.env.ANTHROPIC_API_KEY;
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST", body: JSON.stringify({ transcript: "hi" }) }));
    expect(res.status).toBe(500);
  });

  it("parses topics + actions from tool_use response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(anthropicToolUseResponse(
        ["Q2 pricing"],
        [{ title: "Send proposal", description: "Friday", priority: 2 }]
      )))
    );
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({ transcript: "we discussed Q2 pricing", current_topics: [], current_actions: [] }),
    }));
    const body = await res.json();
    expect(body.topics).toEqual(["Q2 pricing"]);
    expect(body.actions[0].title).toBe("Send proposal");
  });

  it("returns 502 when Anthropic returns non-2xx", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("rate limit", { status: 429 })
    );
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({ transcript: "x", current_topics: [], current_actions: [] }),
    }));
    expect(res.status).toBe(502);
  });

  it("returns empty arrays when no tool_use block in response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ content: [{ type: "text", text: "refusing" }] }))
    );
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({ transcript: "x", current_topics: [], current_actions: [] }),
    }));
    const body = await res.json();
    expect(body.topics).toEqual([]);
    expect(body.actions).toEqual([]);
  });

  it("passes current_topics + current_actions in the Anthropic prompt", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(anthropicToolUseResponse([], [])))
    );
    const { POST } = await import("../route");
    await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({
        transcript: "new text",
        current_topics: ["already discussed"],
        current_actions: [{ title: "existing action", description: "", priority: 3 }],
      }),
    }));
    const callBody = JSON.parse((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(JSON.stringify(callBody)).toContain("already discussed");
    expect(JSON.stringify(callBody)).toContain("existing action");
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test synthesize
```

- [ ] **Step 3: Implement**

`live-nexus/app/api/synthesize/route.ts`:
```typescript
export const runtime = "edge";

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_MODEL = "claude-haiku-4-5";
const ANTHROPIC_VERSION = "2023-06-01";

const UPDATE_SYNTHESIS_TOOL = {
  name: "update_synthesis",
  description:
    "Update the meeting's running list of topics discussed and action items, based on the latest transcript chunk plus the prior state.",
  input_schema: {
    type: "object",
    properties: {
      topics: {
        type: "array",
        description: "Updated list of distinct topics discussed in the meeting so far. Append new topics to the existing list; do not remove prior ones unless they were clearly retracted.",
        items: { type: "string" },
      },
      actions: {
        type: "array",
        description: "Updated list of action items / commitments. Each must be a concrete commitment ('I'll send X', 'Toby will check Y'). Skip vague mentions.",
        items: {
          type: "object",
          properties: {
            title: { type: "string" },
            description: { type: "string" },
            priority: { type: "integer", minimum: 0, maximum: 4 },
          },
          required: ["title", "description", "priority"],
        },
      },
    },
    required: ["topics", "actions"],
  },
};

const SYSTEM_PROMPT = `You are a real-time meeting synthesizer. Given the latest 30 seconds of transcript plus the running state of topics and action items, return the UPDATED full lists.

Rules:
- Topics: short noun phrases ("Q2 pricing tiers", not "we talked about Q2 pricing"). Keep prior topics. Add new ones if discussed.
- Actions: only concrete commitments. Skip philosophical musings.
- Priority: 0=None, 1=Urgent, 2=High (has deadline), 3=Normal, 4=Low.
- Always use the update_synthesis tool. Never reply with prose.`;

export async function POST(req: Request): Promise<Response> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return Response.json({ error: "ANTHROPIC_API_KEY not configured" }, { status: 500 });
  }

  let body: { transcript: string; current_topics: string[]; current_actions: unknown[] };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const userMessage = JSON.stringify({
    new_transcript_chunk: body.transcript,
    current_topics: body.current_topics ?? [],
    current_actions: body.current_actions ?? [],
  });

  try {
    const upstream = await fetch(ANTHROPIC_API_URL, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: ANTHROPIC_MODEL,
        max_tokens: 1024,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: userMessage }],
        tools: [UPDATE_SYNTHESIS_TOOL],
        tool_choice: { type: "tool", name: "update_synthesis" },
      }),
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      console.error("[api/synthesize] Anthropic non-2xx:", upstream.status, text.slice(0, 500));
      return Response.json({ error: "Upstream synthesis failed" }, { status: 502 });
    }

    const data = (await upstream.json()) as { content?: Array<{ type: string; name?: string; input?: unknown }> };
    const toolUse = data.content?.find((b) => b.type === "tool_use" && b.name === "update_synthesis");
    if (!toolUse?.input) {
      return Response.json({ topics: [], actions: [] });
    }
    const input = toolUse.input as { topics: string[]; actions: unknown[] };
    return Response.json({ topics: input.topics ?? [], actions: input.actions ?? [] });
  } catch (e) {
    console.error("[api/synthesize] transport error:", e);
    return Response.json({ error: "Upstream unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test synthesize
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/app/api/synthesize/route.ts live-nexus/app/api/synthesize/__tests__/route.test.ts
git commit -m "feat(live-nexus): /api/synthesize Anthropic Haiku tool-use route (Task 7)"
```

---

## Task 8: `lib/drive-client.ts` (TDD)

**Files:**
- Create: `live-nexus/lib/drive-client.ts`
- Create: `live-nexus/lib/__tests__/drive-client.test.ts`

The Drive API needs a service-account JWT to mint an access token, then uses that token for Drive REST calls. We use the lightweight `googleapis` approach via direct HTTP (no SDK runtime in Edge).

- [ ] **Step 1: Write failing tests**

`live-nexus/lib/__tests__/drive-client.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createDriveFile } from "../drive-client";

describe("createDriveFile", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("posts multipart upload to Drive with parent folder", async () => {
    // First mock: token mint (we'll mock by passing pre-minted token)
    (globalThis.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "file-xyz", webViewLink: "https://drive.google.com/file/d/file-xyz/view" }), { status: 200 })
      );

    const result = await createDriveFile({
      accessToken: "ya29.fake_token",
      folderId: "folder-abc",
      filename: "2026-05-17_acme.md",
      content: "# Acme\n\nbody",
      mimeType: "text/markdown",
    });

    expect(result.fileId).toBe("file-xyz");
    expect(result.webViewLink).toBe("https://drive.google.com/file/d/file-xyz/view");

    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("upload/drive/v3/files");
    const init = call[1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer ya29.fake_token");
  });

  it("includes folder ID as parent in metadata", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "f", webViewLink: "" }))
    );
    await createDriveFile({
      accessToken: "t",
      folderId: "FOLDER123",
      filename: "x.md",
      content: "hi",
      mimeType: "text/markdown",
    });
    const body = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string;
    expect(body).toContain("FOLDER123");
    expect(body).toContain("x.md");
  });

  it("throws on non-2xx response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("forbidden", { status: 403 })
    );
    await expect(createDriveFile({
      accessToken: "t", folderId: "f", filename: "x.md", content: "y", mimeType: "text/markdown",
    })).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test drive-client
```

- [ ] **Step 3: Implement**

`live-nexus/lib/drive-client.ts`:
```typescript
/** Drive REST helpers callable from Edge Runtime.
 * No googleapis npm dep at runtime — direct fetch keeps the edge bundle small. */

const DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";

interface ServiceAccountKey {
  client_email: string;
  private_key: string;
  token_uri?: string;
}

export interface DriveCreateResult {
  fileId: string;
  webViewLink: string;
}

/** Mint a short-lived access token from a service-account JWT.
 * Uses the WebCrypto API available in Edge Runtime. */
export async function mintServiceAccountToken(saKey: ServiceAccountKey): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = {
    iss: saKey.client_email,
    scope: "https://www.googleapis.com/auth/drive.file",
    aud: saKey.token_uri || GOOGLE_TOKEN_URL,
    iat: now,
    exp: now + 3600,
  };

  const enc = (o: object) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unsigned = `${enc(header)}.${enc(claim)}`;

  const pem = saKey.private_key
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const binDer = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "pkcs8",
    binDer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(unsigned)
  );
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const jwt = `${unsigned}.${sigB64}`;

  const tokenRes = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt,
    }),
  });
  if (!tokenRes.ok) {
    const text = await tokenRes.text();
    throw new Error(`Service-account token mint failed: ${tokenRes.status} ${text.slice(0, 200)}`);
  }
  const { access_token } = (await tokenRes.json()) as { access_token: string };
  return access_token;
}

export interface CreateDriveFileInput {
  accessToken: string;
  folderId: string;
  filename: string;
  content: string;
  mimeType: string;
}

export async function createDriveFile(input: CreateDriveFileInput): Promise<DriveCreateResult> {
  const boundary = `boundary_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const metadata = JSON.stringify({
    name: input.filename,
    parents: [input.folderId],
    mimeType: input.mimeType,
  });

  const body =
    `--${boundary}\r\n` +
    `Content-Type: application/json; charset=UTF-8\r\n\r\n` +
    metadata + `\r\n` +
    `--${boundary}\r\n` +
    `Content-Type: ${input.mimeType}\r\n\r\n` +
    input.content + `\r\n` +
    `--${boundary}--`;

  const res = await fetch(`${DRIVE_UPLOAD_URL}&fields=id,webViewLink`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${input.accessToken}`,
      "Content-Type": `multipart/related; boundary=${boundary}`,
    },
    body,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Drive create failed: ${res.status} ${text.slice(0, 200)}`);
  }

  const data = (await res.json()) as { id: string; webViewLink?: string };
  return { fileId: data.id, webViewLink: data.webViewLink ?? "" };
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test drive-client
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/drive-client.ts live-nexus/lib/__tests__/drive-client.test.ts
git commit -m "feat(live-nexus): Drive REST client + service-account JWT mint (Task 8)"
```

---

## Task 9: `/api/save` edge route (TDD)

**Files:**
- Create: `live-nexus/app/api/save/route.ts`
- Create: `live-nexus/app/api/save/__tests__/route.test.ts`

- [ ] **Step 1: Write failing tests**

`live-nexus/app/api/save/__tests__/route.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";

describe("/api/save", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.DRIVE_SERVICE_ACCOUNT_JSON = JSON.stringify({
      client_email: "sa@p.iam.gserviceaccount.com",
      private_key: "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n",
    });
    process.env.DRIVE_FOLDER_ID = "folder-xyz";
  });

  it("returns 500 when DRIVE_SERVICE_ACCOUNT_JSON missing", async () => {
    delete process.env.DRIVE_SERVICE_ACCOUNT_JSON;
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({
        meetingId: "m1", title: "t", startedAt: "2026-05-17T14:00:00+10:00",
        endedAt: "2026-05-17T15:00:00+10:00", transcript: [], topics: [], actions: [], brand: "u",
      }),
    }));
    expect(res.status).toBe(500);
  });

  it("returns 500 when DRIVE_FOLDER_ID missing", async () => {
    delete process.env.DRIVE_FOLDER_ID;
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({
        meetingId: "m1", title: "t", startedAt: "2026-05-17T14:00:00+10:00",
        endedAt: "2026-05-17T15:00:00+10:00", transcript: [], topics: [], actions: [], brand: "u",
      }),
    }));
    expect(res.status).toBe(500);
  });

  it("returns 400 on invalid JSON body", async () => {
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST", body: "not-json" }));
    expect(res.status).toBe(400);
  });

  it("calls mintServiceAccountToken + createDriveFile with composed markdown", async () => {
    const mockMint = vi.fn().mockResolvedValue("ya29.fake");
    const mockCreate = vi.fn().mockResolvedValue({ fileId: "f1", webViewLink: "https://drive/f1" });
    vi.doMock("@/lib/drive-client", () => ({
      mintServiceAccountToken: mockMint,
      createDriveFile: mockCreate,
    }));
    vi.resetModules();
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({
        meetingId: "m1",
        title: "Acme Q2 Pricing",
        startedAt: "2026-05-17T14:32:00+10:00",
        endedAt: "2026-05-17T15:31:42+10:00",
        transcript: [{ timestamp: "14:28", speaker: "A", text: "hi" }],
        topics: ["Q2 pricing"],
        actions: [],
        brand: "unite-group",
      }),
    }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.fileId).toBe("f1");
    expect(body.driveUrl).toBe("https://drive/f1");
    expect(mockMint).toHaveBeenCalledTimes(1);
    expect(mockCreate).toHaveBeenCalledTimes(1);
    const createArgs = mockCreate.mock.calls[0][0];
    expect(createArgs.filename).toMatch(/^2026-05-17_acme-q2-pricing\.md$/);
    expect(createArgs.content).toContain("meeting_id: m1");
    expect(createArgs.content).toContain("# Acme Q2 Pricing");
  });

  it("returns 502 when Drive create throws", async () => {
    vi.doMock("@/lib/drive-client", () => ({
      mintServiceAccountToken: vi.fn().mockResolvedValue("t"),
      createDriveFile: vi.fn().mockRejectedValue(new Error("Drive 403 forbidden")),
    }));
    vi.resetModules();
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", {
      method: "POST",
      body: JSON.stringify({
        meetingId: "m", title: "t", startedAt: "2026-05-17T14:00:00+10:00",
        endedAt: "2026-05-17T14:01:00+10:00", transcript: [], topics: [], actions: [], brand: "u",
      }),
    }));
    expect(res.status).toBe(502);
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test save
```

- [ ] **Step 3: Implement**

`live-nexus/app/api/save/route.ts`:
```typescript
export const runtime = "edge";

import { composeMeetingMarkdown, type MeetingState } from "@/lib/markdown-composer";
import { slugify } from "@/lib/slug";
import { mintServiceAccountToken, createDriveFile } from "@/lib/drive-client";

export async function POST(req: Request): Promise<Response> {
  const saJson = process.env.DRIVE_SERVICE_ACCOUNT_JSON;
  const folderId = process.env.DRIVE_FOLDER_ID;

  if (!saJson) {
    return Response.json({ error: "DRIVE_SERVICE_ACCOUNT_JSON not configured" }, { status: 500 });
  }
  if (!folderId) {
    return Response.json({ error: "DRIVE_FOLDER_ID not configured" }, { status: 500 });
  }

  let state: MeetingState;
  try {
    state = (await req.json()) as MeetingState;
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const markdown = composeMeetingMarkdown(state);
  const dateStr = state.startedAt.slice(0, 10);
  const slug = slugify(state.title || "meeting");
  const filename = `${dateStr}_${slug}.md`;

  try {
    const saKey = JSON.parse(saJson);
    const accessToken = await mintServiceAccountToken(saKey);
    const result = await createDriveFile({
      accessToken,
      folderId,
      filename,
      content: markdown,
      mimeType: "text/markdown",
    });
    return Response.json({ fileId: result.fileId, driveUrl: result.webViewLink });
  } catch (e) {
    console.error("[api/save] Drive save failed:", e);
    return Response.json({ error: String((e as Error).message) }, { status: 502 });
  }
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test save
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/app/api/save/route.ts live-nexus/app/api/save/__tests__/route.test.ts
git commit -m "feat(live-nexus): /api/save Drive markdown upload (Task 9)"
```

---

## Task 10: `lib/indexeddb-session.ts` (TDD)

**Files:**
- Create: `live-nexus/lib/indexeddb-session.ts`
- Create: `live-nexus/lib/__tests__/indexeddb-session.test.ts`

Browser-side crash-recovery store. We use a small wrapper because IndexedDB's raw API is verbose.

- [ ] **Step 1: Add `fake-indexeddb` dev dep**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus
pnpm add -D fake-indexeddb
```

- [ ] **Step 2: Add fake-indexeddb to Vitest setup**

Open `live-nexus/tests/setup.ts` and add at the top:
```typescript
import "fake-indexeddb/auto";
import "@testing-library/jest-dom";
```

- [ ] **Step 3: Write failing tests**

`live-nexus/lib/__tests__/indexeddb-session.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { saveSession, loadSession, clearSession, hasFreshSession } from "../indexeddb-session";

const sample = () => ({
  meetingId: "m1",
  title: "test",
  startedAt: new Date().toISOString(),
  endedAt: "",
  transcript: [{ timestamp: "00:00", speaker: "A", text: "hi" }],
  topics: ["x"],
  actions: [],
  brand: "unite-group",
  lastUpdated: Date.now(),
});

describe("indexeddb-session", () => {
  beforeEach(async () => {
    await clearSession();
  });

  it("saveSession + loadSession round-trip", async () => {
    const s = sample();
    await saveSession(s);
    const loaded = await loadSession();
    expect(loaded?.meetingId).toBe("m1");
    expect(loaded?.transcript[0].text).toBe("hi");
  });

  it("loadSession returns null when empty", async () => {
    expect(await loadSession()).toBeNull();
  });

  it("hasFreshSession true within 10 min", async () => {
    await saveSession(sample());
    expect(await hasFreshSession(10 * 60 * 1000)).toBe(true);
  });

  it("hasFreshSession false when older than maxAge", async () => {
    const s = { ...sample(), lastUpdated: Date.now() - 15 * 60 * 1000 };
    await saveSession(s);
    expect(await hasFreshSession(10 * 60 * 1000)).toBe(false);
  });

  it("clearSession wipes the store", async () => {
    await saveSession(sample());
    await clearSession();
    expect(await loadSession()).toBeNull();
  });
});
```

- [ ] **Step 4: Run, expect failure**

```bash
pnpm test indexeddb-session
```

- [ ] **Step 5: Implement**

`live-nexus/lib/indexeddb-session.ts`:
```typescript
import type { Action, TranscriptLine } from "./markdown-composer";

export interface StoredSession {
  meetingId: string;
  title: string;
  startedAt: string;
  endedAt: string;
  transcript: TranscriptLine[];
  topics: string[];
  actions: Action[];
  brand: string;
  lastUpdated: number;
}

const DB_NAME = "live-nexus";
const STORE = "session";
const KEY = "current";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveSession(session: StoredSession): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put({ ...session, lastUpdated: Date.now() }, KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function loadSession(): Promise<StoredSession | null> {
  const db = await openDb();
  const result = await new Promise<StoredSession | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(KEY);
    req.onsuccess = () => resolve(req.result as StoredSession | undefined);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return result ?? null;
}

export async function clearSession(): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function hasFreshSession(maxAgeMs: number): Promise<boolean> {
  const s = await loadSession();
  if (!s) return false;
  return Date.now() - s.lastUpdated < maxAgeMs;
}
```

- [ ] **Step 6: Tests pass**

```bash
pnpm test indexeddb-session
```
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/indexeddb-session.ts live-nexus/lib/__tests__/indexeddb-session.test.ts live-nexus/tests/setup.ts live-nexus/package.json live-nexus/pnpm-lock.yaml
git commit -m "feat(live-nexus): IndexedDB crash-recovery session store (Task 10)"
```

---

## Task 11: `lib/assemblyai-client.ts` (TDD)

**Files:**
- Create: `live-nexus/lib/assemblyai-client.ts`
- Create: `live-nexus/lib/__tests__/assemblyai-client.test.ts`

Browser wrapper that opens the AssemblyAI WebSocket and emits typed events.

- [ ] **Step 1: Add `mock-socket` dev dep**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus
pnpm add -D mock-socket
```

- [ ] **Step 2: Write failing tests**

`live-nexus/lib/__tests__/assemblyai-client.test.ts`:
```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { Server } from "mock-socket";
import { AssemblyAiClient } from "../assemblyai-client";

const WS_URL = "wss://api.assemblyai.com/v2/realtime/ws";

describe("AssemblyAiClient", () => {
  let server: Server;

  beforeEach(() => {
    server = new Server(WS_URL + "?token=tmp_abc");
    vi.useFakeTimers();
  });

  afterEach(() => {
    server.stop();
    vi.useRealTimers();
  });

  it("emits partial transcript events", async () => {
    const partials: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(JSON.stringify({
          message_type: "PartialTranscript",
          text: "hello world",
          words: [],
        }));
      }, 10);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("partial", (e) => partials.push(e.text));
    client.connect();

    await vi.advanceTimersByTimeAsync(50);
    expect(partials).toContain("hello world");
  });

  it("emits final transcript events with speaker", async () => {
    const finals: Array<{ text: string; speaker: string }> = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(JSON.stringify({
          message_type: "FinalTranscript",
          text: "this is final",
          speaker: "A",
          audio_start: 0,
          audio_end: 1500,
        }));
      }, 10);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("final", (e) => finals.push({ text: e.text, speaker: e.speaker }));
    client.connect();

    await vi.advanceTimersByTimeAsync(50);
    expect(finals[0]).toEqual({ text: "this is final", speaker: "A" });
  });

  it("emits disconnect event on socket close", async () => {
    const events: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => socket.close(), 10);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("disconnect", () => events.push("disconnect"));
    client.connect();

    await vi.advanceTimersByTimeAsync(50);
    expect(events).toContain("disconnect");
  });

  it("close() prevents further events", async () => {
    const partials: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(JSON.stringify({ message_type: "PartialTranscript", text: "after close", words: [] }));
      }, 30);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("partial", (e) => partials.push(e.text));
    client.connect();
    client.close();

    await vi.advanceTimersByTimeAsync(100);
    expect(partials).not.toContain("after close");
  });
});
```

- [ ] **Step 3: Run, expect failure**

```bash
pnpm test assemblyai-client
```

- [ ] **Step 4: Implement**

`live-nexus/lib/assemblyai-client.ts`:
```typescript
/** Browser-side AssemblyAI realtime WebSocket wrapper.
 * Emits "partial" / "final" / "disconnect" / "error" events. */

export interface PartialEvent {
  text: string;
  words: Array<{ text: string; start: number; end: number; confidence: number }>;
}

export interface FinalEvent {
  text: string;
  speaker: string;
  audioStart: number;
  audioEnd: number;
}

export type AssemblyAiEvents = {
  partial: PartialEvent;
  final: FinalEvent;
  disconnect: { code: number; reason: string };
  error: { message: string };
};

type Listener<K extends keyof AssemblyAiEvents> = (e: AssemblyAiEvents[K]) => void;

export interface AssemblyAiClientOptions {
  wsUrl: string;
  token: string;
}

export class AssemblyAiClient {
  private ws: WebSocket | null = null;
  private listeners: { [K in keyof AssemblyAiEvents]?: Listener<K>[] } = {};
  private closed = false;

  constructor(private opts: AssemblyAiClientOptions) {}

  on<K extends keyof AssemblyAiEvents>(event: K, fn: Listener<K>): void {
    (this.listeners[event] ??= [] as Listener<K>[]).push(fn);
  }

  private emit<K extends keyof AssemblyAiEvents>(event: K, payload: AssemblyAiEvents[K]): void {
    if (this.closed) return;
    for (const fn of this.listeners[event] ?? []) fn(payload);
  }

  connect(): void {
    const url = `${this.opts.wsUrl}?token=${encodeURIComponent(this.opts.token)}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string);
        if (data.message_type === "PartialTranscript") {
          this.emit("partial", { text: data.text, words: data.words ?? [] });
        } else if (data.message_type === "FinalTranscript") {
          this.emit("final", {
            text: data.text,
            speaker: data.speaker ?? "?",
            audioStart: data.audio_start ?? 0,
            audioEnd: data.audio_end ?? 0,
          });
        }
      } catch (e) {
        this.emit("error", { message: `parse error: ${(e as Error).message}` });
      }
    };
    this.ws.onclose = (ev) => {
      this.emit("disconnect", { code: ev.code, reason: ev.reason });
    };
    this.ws.onerror = () => {
      this.emit("error", { message: "WebSocket error" });
    };
  }

  /** Send 16-bit PCM audio chunk to AssemblyAI. */
  sendAudio(chunk: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(chunk);
    }
  }

  close(): void {
    this.closed = true;
    if (this.ws) {
      try {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ terminate_session: true }));
        }
      } catch {
        /* ignore */
      }
      this.ws.close();
      this.ws = null;
    }
  }
}
```

- [ ] **Step 5: Tests pass**

```bash
pnpm test assemblyai-client
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/assemblyai-client.ts live-nexus/lib/__tests__/assemblyai-client.test.ts live-nexus/package.json live-nexus/pnpm-lock.yaml
git commit -m "feat(live-nexus): AssemblyAI realtime WS client (Task 11)"
```

---

## Task 12: `lib/synthesis-poller.ts` (TDD)

**Files:**
- Create: `live-nexus/lib/synthesis-poller.ts`
- Create: `live-nexus/lib/__tests__/synthesis-poller.test.ts`

- [ ] **Step 1: Write failing tests**

`live-nexus/lib/__tests__/synthesis-poller.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SynthesisPoller } from "../synthesis-poller";

describe("SynthesisPoller", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function mockOk(payload: object) {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(payload), { status: 200 })
    );
  }

  it("calls /api/synthesize after intervalMs", async () => {
    mockOk({ topics: ["X"], actions: [] });
    const onUpdate = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "hi", topics: [], actions: [] }),
      onUpdate,
    });
    poller.start();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(0);
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/synthesize", expect.objectContaining({ method: "POST" }));
    expect(onUpdate).toHaveBeenCalledWith({ topics: ["X"], actions: [] });
    poller.stop();
  });

  it("passes current state in request body", async () => {
    mockOk({ topics: [], actions: [] });
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "new chunk", topics: ["prior"], actions: [{ title: "a", description: "", priority: 3 }] }),
      onUpdate: vi.fn(),
    });
    poller.start();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(0);
    const callBody = JSON.parse((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(callBody.transcript).toBe("new chunk");
    expect(callBody.current_topics).toEqual(["prior"]);
    expect(callBody.current_actions[0].title).toBe("a");
    poller.stop();
  });

  it("emits pause event after 3 consecutive failures", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("net"));
    const onPause = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "x", topics: [], actions: [] }),
      onUpdate: vi.fn(),
      onPause,
    });
    poller.start();
    for (let i = 0; i < 3; i++) {
      await vi.advanceTimersByTimeAsync(1000);
      await vi.advanceTimersByTimeAsync(0);
    }
    expect(onPause).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("stop() prevents further polls", async () => {
    mockOk({ topics: [], actions: [] });
    const onUpdate = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "x", topics: [], actions: [] }),
      onUpdate,
    });
    poller.start();
    poller.stop();
    await vi.advanceTimersByTimeAsync(2000);
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("flush() forces an immediate poll", async () => {
    mockOk({ topics: ["forced"], actions: [] });
    const onUpdate = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 100000,
      getState: () => ({ transcript: "x", topics: [], actions: [] }),
      onUpdate,
    });
    poller.start();
    await poller.flush();
    expect(onUpdate).toHaveBeenCalledWith({ topics: ["forced"], actions: [] });
    poller.stop();
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test synthesis-poller
```

- [ ] **Step 3: Implement**

`live-nexus/lib/synthesis-poller.ts`:
```typescript
import type { Action } from "./markdown-composer";

export interface SynthesisPollerOptions {
  intervalMs: number;
  getState: () => { transcript: string; topics: string[]; actions: Action[] };
  onUpdate: (update: { topics: string[]; actions: Action[] }) => void;
  onPause?: () => void;
  onResume?: () => void;
}

const FAIL_PAUSE_THRESHOLD = 3;

export class SynthesisPoller {
  private timer: ReturnType<typeof setInterval> | null = null;
  private stopped = false;
  private consecutiveFailures = 0;
  private paused = false;

  constructor(private opts: SynthesisPollerOptions) {}

  start(): void {
    this.stopped = false;
    this.timer = setInterval(() => void this.tick(), this.opts.intervalMs);
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  /** Force an immediate poll, bypassing the interval. */
  async flush(): Promise<void> {
    await this.tick();
  }

  private async tick(): Promise<void> {
    if (this.stopped) return;
    const state = this.opts.getState();
    try {
      const res = await fetch("/api/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: state.transcript,
          current_topics: state.topics,
          current_actions: state.actions,
        }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = (await res.json()) as { topics: string[]; actions: Action[] };
      if (this.stopped) return;
      this.consecutiveFailures = 0;
      if (this.paused) {
        this.paused = false;
        this.opts.onResume?.();
      }
      this.opts.onUpdate(data);
    } catch (e) {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= FAIL_PAUSE_THRESHOLD && !this.paused) {
        this.paused = true;
        this.opts.onPause?.();
      }
      console.warn("[synthesis-poller] tick failed:", e);
    }
  }
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test synthesis-poller
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/lib/synthesis-poller.ts live-nexus/lib/__tests__/synthesis-poller.test.ts
git commit -m "feat(live-nexus): 30s synthesis poller with 3-strike pause (Task 12)"
```

---

## Task 13: Tailwind brand setup + globals.css

**Files:**
- Modify: `live-nexus/tailwind.config.ts`
- Modify: `live-nexus/app/globals.css`

- [ ] **Step 1: Update Tailwind config**

Replace `live-nexus/tailwind.config.ts` content:
```typescript
import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0e1014",
        surface: "#15181f",
        hairline: "#2a2d35",
        ink: { DEFAULT: "#f4ecd8", muted: "#8c8a85" },
        accent: { DEFAULT: "#b30000", muted: "#7a0000" },
      },
      fontFamily: {
        body: ["Inter", "-apple-system", "system-ui", "sans-serif"],
        brand: ["Charter", '"Iowan Old Style"', "Georgia", "serif"],
        mono: ['"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
    },
  },
} satisfies Config;
```

- [ ] **Step 2: Update globals.css**

Replace `live-nexus/app/globals.css` content:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html { background: #0e1014; color: #f4ecd8; }
  body { font-family: Inter, -apple-system, system-ui, sans-serif; }
  ::selection { background: #b30000; color: #f4ecd8; }
}

@layer components {
  .live-dot {
    width: 10px; height: 10px; border-radius: 9999px; background: #b30000;
    animation: live-pulse 1s ease-in-out infinite;
  }
  .live-dot--paused { background: #8c8a85; animation: none; }
  .live-cursor {
    display: inline-block; width: 2px; height: 1em; background: #b30000; margin-left: 2px;
    animation: cursor-blink 1s steps(2) infinite;
  }
}

@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
@keyframes cursor-blink {
  50% { opacity: 0; }
}
```

- [ ] **Step 3: Verify build**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm build
```
Expected: build succeeds with no Tailwind errors.

- [ ] **Step 4: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/tailwind.config.ts live-nexus/app/globals.css
git commit -m "feat(live-nexus): Tailwind brand tokens + animations (Task 13)"
```

---

## Task 14: `components/MeetingHeader.tsx`

**Files:**
- Create: `live-nexus/components/MeetingHeader.tsx`
- Create: `live-nexus/components/__tests__/MeetingHeader.test.tsx`

- [ ] **Step 1: Write failing tests**

`live-nexus/components/__tests__/MeetingHeader.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MeetingHeader } from "../MeetingHeader";

describe("MeetingHeader", () => {
  it("shows brand wordmark", () => {
    render(<MeetingHeader state="recording" elapsedSeconds={0} clockTime="14:32" />);
    expect(screen.getByText(/UNITE GROUP NEXUS/i)).toBeInTheDocument();
  });

  it("renders elapsed timer in mm:ss for short meetings", () => {
    render(<MeetingHeader state="recording" elapsedSeconds={62} clockTime="14:33" />);
    expect(screen.getByText("01:02")).toBeInTheDocument();
  });

  it("renders elapsed timer in h:mm:ss for long meetings", () => {
    render(<MeetingHeader state="recording" elapsedSeconds={3725} clockTime="14:33" />);
    expect(screen.getByText("1:02:05")).toBeInTheDocument();
  });

  it("LIVE dot is animated in recording state", () => {
    const { container } = render(<MeetingHeader state="recording" elapsedSeconds={0} clockTime="14:32" />);
    const dot = container.querySelector(".live-dot");
    expect(dot).toBeTruthy();
    expect(dot?.classList.contains("live-dot--paused")).toBe(false);
  });

  it("LIVE dot is paused (grey) when state is ended", () => {
    const { container } = render(<MeetingHeader state="ended" elapsedSeconds={3600} clockTime="14:32" />);
    const dot = container.querySelector(".live-dot--paused");
    expect(dot).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test MeetingHeader
```

- [ ] **Step 3: Implement**

`live-nexus/components/MeetingHeader.tsx`:
```typescript
export type MeetingHeaderState = "preflight" | "recording" | "paused" | "reconnecting" | "ended";

export interface MeetingHeaderProps {
  state: MeetingHeaderState;
  elapsedSeconds: number;
  clockTime: string;        // "14:32"
}

function formatElapsed(s: number): string {
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function MeetingHeader({ state, elapsedSeconds, clockTime }: MeetingHeaderProps) {
  const dotPaused = state === "ended" || state === "paused";
  return (
    <header className="flex items-center justify-between border-b border-hairline px-6 py-4">
      <div className="flex items-center gap-4">
        <span className={`live-dot ${dotPaused ? "live-dot--paused" : ""}`} aria-label="recording status" />
        <h1 className="font-brand italic text-lg tracking-wide text-ink">UNITE GROUP NEXUS</h1>
      </div>
      <div className="flex items-center gap-4 font-mono text-sm text-ink-muted tabular-nums">
        <span>{clockTime}</span>
        <span aria-hidden>·</span>
        <span className="text-ink">{formatElapsed(elapsedSeconds)}</span>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test MeetingHeader
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/components/MeetingHeader.tsx live-nexus/components/__tests__/MeetingHeader.test.tsx
git commit -m "feat(live-nexus): MeetingHeader with LIVE dot + timer (Task 14)"
```

---

## Task 15: `components/TranscriptStream.tsx`

**Files:**
- Create: `live-nexus/components/TranscriptStream.tsx`
- Create: `live-nexus/components/__tests__/TranscriptStream.test.tsx`

- [ ] **Step 1: Write failing tests**

`live-nexus/components/__tests__/TranscriptStream.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TranscriptStream } from "../TranscriptStream";

describe("TranscriptStream", () => {
  it("renders finalized transcript lines with timestamps", () => {
    render(
      <TranscriptStream
        lines={[
          { timestamp: "14:28", speaker: "A", text: "hello there" },
          { timestamp: "14:30", speaker: "B", text: "how are you" },
        ]}
        partial=""
      />
    );
    expect(screen.getByText(/hello there/)).toBeInTheDocument();
    expect(screen.getByText(/how are you/)).toBeInTheDocument();
    expect(screen.getByText(/Speaker A/i)).toBeInTheDocument();
  });

  it("renders partial transcript with live cursor", () => {
    const { container } = render(
      <TranscriptStream lines={[]} partial="this is being said" />
    );
    expect(screen.getByText(/this is being said/)).toBeInTheDocument();
    expect(container.querySelector(".live-cursor")).toBeTruthy();
  });

  it("does not render cursor when no partial", () => {
    const { container } = render(
      <TranscriptStream lines={[{ timestamp: "14:28", speaker: "A", text: "done" }]} partial="" />
    );
    expect(container.querySelector(".live-cursor")).toBeFalsy();
  });

  it("renders empty state when no lines and no partial", () => {
    render(<TranscriptStream lines={[]} partial="" />);
    expect(screen.getByText(/listening/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test TranscriptStream
```

- [ ] **Step 3: Implement**

`live-nexus/components/TranscriptStream.tsx`:
```typescript
"use client";
import { useEffect, useRef } from "react";
import type { TranscriptLine } from "@/lib/markdown-composer";

export interface TranscriptStreamProps {
  lines: TranscriptLine[];
  partial: string;
}

export function TranscriptStream({ lines, partial }: TranscriptStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, partial]);

  const isEmpty = lines.length === 0 && !partial;

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto rounded-lg border border-hairline bg-surface p-6 text-ink"
    >
      <div className="mb-4 text-xs uppercase tracking-[0.1em] text-ink-muted">Transcript</div>
      {isEmpty && (
        <p className="text-ink-muted italic">Listening…</p>
      )}
      <div className="space-y-4">
        {lines.map((line, i) => (
          <div key={i}>
            <div className="mb-1 text-xs uppercase tracking-[0.05em] text-ink-muted">
              [{line.timestamp}] Speaker {line.speaker}
            </div>
            <p className="text-[17px] leading-relaxed">{line.text}</p>
          </div>
        ))}
        {partial && (
          <div>
            <p className="text-[17px] leading-relaxed text-ink-muted">
              {partial}
              <span className="live-cursor" aria-hidden />
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test TranscriptStream
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/components/TranscriptStream.tsx live-nexus/components/__tests__/TranscriptStream.test.tsx
git commit -m "feat(live-nexus): TranscriptStream with live cursor (Task 15)"
```

---

## Task 16: `components/SynthesisSidebar.tsx`

**Files:**
- Create: `live-nexus/components/SynthesisSidebar.tsx`
- Create: `live-nexus/components/__tests__/SynthesisSidebar.test.tsx`

- [ ] **Step 1: Write failing tests**

`live-nexus/components/__tests__/SynthesisSidebar.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SynthesisSidebar } from "../SynthesisSidebar";

describe("SynthesisSidebar", () => {
  it("renders topics list", () => {
    render(
      <SynthesisSidebar
        topics={["Q2 pricing", "Onboarding"]}
        actions={[]}
        synthesisPaused={false}
      />
    );
    expect(screen.getByText(/Q2 pricing/i)).toBeInTheDocument();
    expect(screen.getByText(/Onboarding/i)).toBeInTheDocument();
  });

  it("renders actions with description + priority badge", () => {
    render(
      <SynthesisSidebar
        topics={[]}
        actions={[
          { title: "Send proposal", description: "by Friday", priority: 2 },
          { title: "Review numbers", description: "", priority: 4 },
        ]}
        synthesisPaused={false}
      />
    );
    expect(screen.getByText(/Send proposal/i)).toBeInTheDocument();
    expect(screen.getByText(/by Friday/i)).toBeInTheDocument();
    expect(screen.getByText(/HIGH/i)).toBeInTheDocument();
    expect(screen.getByText(/LOW/i)).toBeInTheDocument();
  });

  it("renders synthesis-paused pill when paused", () => {
    render(<SynthesisSidebar topics={[]} actions={[]} synthesisPaused={true} />);
    expect(screen.getByText(/synthesis paused/i)).toBeInTheDocument();
  });

  it("renders empty-state when no data", () => {
    render(<SynthesisSidebar topics={[]} actions={[]} synthesisPaused={false} />);
    expect(screen.getAllByText(/none yet/i).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test SynthesisSidebar
```

- [ ] **Step 3: Implement**

`live-nexus/components/SynthesisSidebar.tsx`:
```typescript
import type { Action } from "@/lib/markdown-composer";

export interface SynthesisSidebarProps {
  topics: string[];
  actions: Action[];
  synthesisPaused: boolean;
}

const PRIORITY_LABEL: Record<number, string> = {
  0: "", 1: "URGENT", 2: "HIGH", 3: "", 4: "LOW",
};

export function SynthesisSidebar({ topics, actions, synthesisPaused }: SynthesisSidebarProps) {
  return (
    <aside className="flex h-full flex-col gap-4">
      <section className="rounded-lg border border-hairline bg-surface p-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-muted">
            Topics Discussed
          </h2>
          {synthesisPaused && (
            <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent">
              synthesis paused
            </span>
          )}
        </div>
        {topics.length === 0 ? (
          <p className="text-sm italic text-ink-muted">None yet.</p>
        ) : (
          <ul className="space-y-2">
            {topics.map((t, i) => (
              <li key={i} className="text-sm text-ink">
                <span className="text-ink-muted">•</span> {t}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex-1 rounded-lg border border-hairline bg-surface p-6">
        <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.1em] text-ink-muted">
          Action Items
        </h2>
        {actions.length === 0 ? (
          <p className="text-sm italic text-ink-muted">None yet.</p>
        ) : (
          <ul className="space-y-3">
            {actions.map((a, i) => (
              <li key={i} className="text-sm text-ink">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-accent">▸</span>
                  <div className="flex-1">
                    <div className="font-medium">{a.title}</div>
                    {a.description && (
                      <div className="mt-0.5 text-ink-muted">{a.description}</div>
                    )}
                    {PRIORITY_LABEL[a.priority] && (
                      <span className="mt-1 inline-block text-[10px] uppercase tracking-wider text-accent">
                        {PRIORITY_LABEL[a.priority]}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test SynthesisSidebar
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/components/SynthesisSidebar.tsx live-nexus/components/__tests__/SynthesisSidebar.test.tsx
git commit -m "feat(live-nexus): SynthesisSidebar with topics + actions + paused pill (Task 16)"
```

---

## Task 17: `components/ConnectionStatus.tsx` + `PreflightCheck.tsx`

**Files:**
- Create: `live-nexus/components/ConnectionStatus.tsx`
- Create: `live-nexus/components/PreflightCheck.tsx`
- Create: `live-nexus/components/__tests__/ConnectionStatus.test.tsx`
- Create: `live-nexus/components/__tests__/PreflightCheck.test.tsx`

- [ ] **Step 1: Write failing tests**

`live-nexus/components/__tests__/ConnectionStatus.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConnectionStatus } from "../ConnectionStatus";

describe("ConnectionStatus", () => {
  it("renders Reconnecting banner when state is reconnecting", () => {
    render(<ConnectionStatus state="reconnecting" />);
    expect(screen.getByText(/Reconnecting/i)).toBeInTheDocument();
  });

  it("renders nothing when state is connected", () => {
    const { container } = render(<ConnectionStatus state="connected" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders error banner when state is error", () => {
    render(<ConnectionStatus state="error" message="Network unreachable" />);
    expect(screen.getByText(/Network unreachable/)).toBeInTheDocument();
  });
});
```

`live-nexus/components/__tests__/PreflightCheck.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PreflightCheck } from "../PreflightCheck";

describe("PreflightCheck", () => {
  it("renders all 3 checks", () => {
    render(<PreflightCheck mic="ok" network="ok" browser="ok" />);
    expect(screen.getByText(/microphone/i)).toBeInTheDocument();
    expect(screen.getByText(/network/i)).toBeInTheDocument();
    expect(screen.getByText(/browser/i)).toBeInTheDocument();
  });

  it("shows error state for failed check", () => {
    render(<PreflightCheck mic="fail" network="ok" browser="ok" />);
    const micRow = screen.getByText(/microphone/i).closest("li");
    expect(micRow?.textContent).toContain("✗");
  });
});
```

- [ ] **Step 2: Run, expect failure**

```bash
pnpm test ConnectionStatus
pnpm test PreflightCheck
```

- [ ] **Step 3: Implement**

`live-nexus/components/ConnectionStatus.tsx`:
```typescript
export type ConnectionState = "connected" | "reconnecting" | "error";

export interface ConnectionStatusProps {
  state: ConnectionState;
  message?: string;
}

export function ConnectionStatus({ state, message }: ConnectionStatusProps) {
  if (state === "connected") return null;
  const isError = state === "error";
  return (
    <div
      role="alert"
      className={`fixed left-1/2 top-20 z-50 -translate-x-1/2 rounded-lg border px-4 py-2 text-sm
        ${isError ? "border-accent bg-accent/10 text-ink" : "border-ink-muted bg-surface text-ink-muted"}`}
    >
      {isError ? message ?? "Connection error" : "Reconnecting to transcription service…"}
    </div>
  );
}
```

`live-nexus/components/PreflightCheck.tsx`:
```typescript
export type CheckState = "pending" | "ok" | "fail";

export interface PreflightCheckProps {
  mic: CheckState;
  network: CheckState;
  browser: CheckState;
}

function Icon({ state }: { state: CheckState }) {
  if (state === "ok") return <span className="text-accent">✓</span>;
  if (state === "fail") return <span className="text-accent">✗</span>;
  return <span className="text-ink-muted">…</span>;
}

export function PreflightCheck({ mic, network, browser }: PreflightCheckProps) {
  return (
    <ul className="space-y-2 text-sm text-ink-muted">
      <li className="flex items-center gap-3">
        <Icon state={mic} /> <span>Microphone</span>
      </li>
      <li className="flex items-center gap-3">
        <Icon state={network} /> <span>Network — AssemblyAI reachable</span>
      </li>
      <li className="flex items-center gap-3">
        <Icon state={browser} /> <span>Browser supports recording</span>
      </li>
    </ul>
  );
}
```

- [ ] **Step 4: Tests pass**

```bash
pnpm test
```
Expected: full suite passes.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/components/ConnectionStatus.tsx live-nexus/components/PreflightCheck.tsx live-nexus/components/__tests__/ConnectionStatus.test.tsx live-nexus/components/__tests__/PreflightCheck.test.tsx
git commit -m "feat(live-nexus): ConnectionStatus + PreflightCheck components (Task 17)"
```

---

## Task 18: `app/layout.tsx` + `app/page.tsx` (landing)

**Files:**
- Modify: `live-nexus/app/layout.tsx`
- Modify: `live-nexus/app/page.tsx`

- [ ] **Step 1: Implement layout**

Replace `live-nexus/app/layout.tsx`:
```typescript
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Unite Group Nexus — Live Meeting Notes",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="bg-bg text-ink">
      <body className="font-body min-h-screen">{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: Implement landing page**

Replace `live-nexus/app/page.tsx`:
```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PreflightCheck, type CheckState } from "@/components/PreflightCheck";

function uuidv4(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  arr[6] = (arr[6] & 0x0f) | 0x40;
  arr[8] = (arr[8] & 0x3f) | 0x80;
  const hex = Array.from(arr).map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export default function LandingPage() {
  const router = useRouter();
  const [mic, setMic] = useState<CheckState>("pending");
  const [network, setNetwork] = useState<CheckState>("pending");
  const [browser, setBrowser] = useState<CheckState>("pending");

  useEffect(() => {
    const supportsMedia =
      typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && !!window.WebSocket;
    setBrowser(supportsMedia ? "ok" : "fail");

    navigator.mediaDevices
      ?.enumerateDevices()
      .then((devices) => {
        const hasMic = devices.some((d) => d.kind === "audioinput");
        setMic(hasMic ? "ok" : "fail");
      })
      .catch(() => setMic("fail"));

    fetch("/api/session", { method: "POST" })
      .then((res) => setNetwork(res.ok ? "ok" : "fail"))
      .catch(() => setNetwork("fail"));
  }, []);

  const allOk = mic === "ok" && network === "ok" && browser === "ok";

  const start = () => {
    const id = uuidv4();
    router.push(`/m/${id}`);
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-8 px-6">
      <header className="text-center">
        <h1 className="font-brand text-3xl italic">UNITE GROUP NEXUS</h1>
        <p className="mt-2 text-ink-muted">Live meeting notes</p>
      </header>

      <button
        type="button"
        onClick={start}
        disabled={!allOk}
        className="rounded-lg border-2 border-accent bg-accent/10 px-12 py-6 text-lg uppercase tracking-wider text-ink transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        ● Start Meeting
      </button>

      <PreflightCheck mic={mic} network={network} browser={browser} />

      <p className="max-w-md text-center text-sm text-ink-muted">
        Microphone access required. Recording stays on this device until you click End Meeting.
      </p>
    </main>
  );
}
```

- [ ] **Step 3: Verify build**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm build
```
Expected: build succeeds.

- [ ] **Step 4: Manual sanity check**

```bash
pnpm dev
```
Open http://localhost:3000. Expect: brand chrome visible, three preflight rows (microphone fails likely without permissions in jsdom but the page renders).
Ctrl+C to stop.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/app/layout.tsx live-nexus/app/page.tsx
git commit -m "feat(live-nexus): landing page with preflight + Start Meeting (Task 18)"
```

---

## Task 19: `app/m/[id]/page.tsx` (active meeting SPA)

**Files:**
- Create: `live-nexus/app/m/[id]/page.tsx`

This is the integration page — assembles all components and wires AssemblyAI + synthesis poller + save. Long file but no new logic; it's the wiring layer.

- [ ] **Step 1: Implement**

`live-nexus/app/m/[id]/page.tsx`:
```typescript
"use client";

import { useEffect, useRef, useState, use } from "react";
import { MeetingHeader, type MeetingHeaderState } from "@/components/MeetingHeader";
import { TranscriptStream } from "@/components/TranscriptStream";
import { SynthesisSidebar } from "@/components/SynthesisSidebar";
import { ConnectionStatus, type ConnectionState } from "@/components/ConnectionStatus";
import { AssemblyAiClient } from "@/lib/assemblyai-client";
import { SynthesisPoller } from "@/lib/synthesis-poller";
import { saveSession, clearSession } from "@/lib/indexeddb-session";
import type { Action, TranscriptLine } from "@/lib/markdown-composer";

const SYNTHESIS_INTERVAL_MS = 30_000;

export default function MeetingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [headerState, setHeaderState] = useState<MeetingHeaderState>("preflight");
  const [connection, setConnection] = useState<ConnectionState>("connected");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [partial, setPartial] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [synthesisPaused, setSynthesisPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [clockTime, setClockTime] = useState("");
  const [endedFileUrl, setEndedFileUrl] = useState<string | null>(null);

  const startedAtRef = useRef<string>("");
  const aaiRef = useRef<AssemblyAiClient | null>(null);
  const pollerRef = useRef<SynthesisPoller | null>(null);

  function fmtClock(d: Date) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  function fmtTs(ms: number) {
    const totalS = Math.floor(ms / 1000);
    const m = Math.floor(totalS / 60);
    const s = totalS % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  useEffect(() => {
    setClockTime(fmtClock(new Date()));
    const i = setInterval(() => {
      setClockTime(fmtClock(new Date()));
      setElapsed((e) => (headerState === "recording" ? e + 1 : e));
    }, 1000);
    return () => clearInterval(i);
  }, [headerState]);

  async function startMeeting() {
    try {
      // 1. Mint AssemblyAI token
      const sessionRes = await fetch("/api/session", { method: "POST" });
      if (!sessionRes.ok) throw new Error("Failed to mint AssemblyAI token");
      const { token, ws_url } = (await sessionRes.json()) as { token: string; ws_url: string };

      // 2. Mic stream
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });

      // 3. AssemblyAI client
      const aai = new AssemblyAiClient({ wsUrl: ws_url, token });
      aaiRef.current = aai;
      aai.on("partial", (e) => setPartial(e.text));
      aai.on("final", (e) => {
        setPartial("");
        setLines((prev) => {
          const ts = fmtTs(e.audioStart);
          return [...prev, { timestamp: ts, speaker: e.speaker, text: e.text }];
        });
      });
      aai.on("disconnect", () => setConnection("reconnecting"));
      aai.on("error", () => setConnection("error"));
      aai.connect();

      // 4. Audio worklet — feed PCM-16 chunks to AssemblyAI
      const audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(audioContext.destination);
      processor.onaudioprocess = (ev) => {
        const f32 = ev.inputBuffer.getChannelData(0);
        const i16 = new Int16Array(f32.length);
        for (let i = 0; i < f32.length; i++) {
          const v = Math.max(-1, Math.min(1, f32[i]));
          i16[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
        }
        aai.sendAudio(i16.buffer);
      };

      // 5. Synthesis poller
      const poller = new SynthesisPoller({
        intervalMs: SYNTHESIS_INTERVAL_MS,
        getState: () => ({
          transcript: lines.map((l) => `[${l.timestamp}] ${l.speaker}: ${l.text}`).join("\n"),
          topics,
          actions,
        }),
        onUpdate: ({ topics: newT, actions: newA }) => {
          setTopics(newT);
          setActions(newA);
        },
        onPause: () => setSynthesisPaused(true),
        onResume: () => setSynthesisPaused(false),
      });
      pollerRef.current = poller;
      poller.start();

      startedAtRef.current = new Date().toISOString();
      setHeaderState("recording");
    } catch (e) {
      console.error("startMeeting failed:", e);
      setConnection("error");
    }
  }

  async function endMeeting() {
    pollerRef.current?.stop();
    await pollerRef.current?.flush();
    aaiRef.current?.close();
    setHeaderState("ended");

    try {
      const res = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meetingId: id,
          title: topics[0] ?? "Meeting",
          startedAt: startedAtRef.current,
          endedAt: new Date().toISOString(),
          transcript: lines,
          topics,
          actions,
          brand: "unite-group",
        }),
      });
      if (!res.ok) throw new Error("save failed");
      const data = (await res.json()) as { driveUrl: string };
      setEndedFileUrl(data.driveUrl);
      await clearSession();
    } catch (e) {
      console.error("save failed:", e);
      setConnection("error");
    }
  }

  // Periodic IndexedDB persistence
  useEffect(() => {
    if (headerState !== "recording") return;
    const i = setInterval(() => {
      void saveSession({
        meetingId: id,
        title: topics[0] ?? "Meeting",
        startedAt: startedAtRef.current,
        endedAt: "",
        transcript: lines,
        topics,
        actions,
        brand: "unite-group",
        lastUpdated: Date.now(),
      });
    }, 5000);
    return () => clearInterval(i);
  }, [headerState, id, lines, topics, actions]);

  return (
    <main className="flex h-screen flex-col">
      <MeetingHeader state={headerState} elapsedSeconds={elapsed} clockTime={clockTime} />
      <ConnectionStatus state={connection} />

      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        <div className="basis-[60%]">
          <TranscriptStream lines={lines} partial={partial} />
        </div>
        <div className="basis-[40%]">
          <SynthesisSidebar topics={topics} actions={actions} synthesisPaused={synthesisPaused} />
        </div>
      </div>

      <footer className="flex items-center justify-between border-t border-hairline px-6 py-3 text-xs text-ink-muted">
        <span>● {connection === "connected" ? "Connected" : connection}</span>
        {headerState !== "recording" && headerState !== "ended" && (
          <button
            onClick={startMeeting}
            className="rounded border border-accent px-4 py-2 text-ink hover:bg-accent/10"
          >
            ● Start Meeting
          </button>
        )}
        {headerState === "recording" && (
          <button
            onClick={endMeeting}
            className="rounded border border-accent px-4 py-2 text-ink hover:bg-accent/10"
          >
            End Meeting
          </button>
        )}
        {headerState === "ended" && endedFileUrl && (
          <a
            href={endedFileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded border border-accent px-4 py-2 text-ink hover:bg-accent/10"
          >
            Open in Drive
          </a>
        )}
      </footer>
    </main>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm build
```
Expected: build succeeds.

- [ ] **Step 3: Manual sanity check**

```bash
pnpm dev
```
Open http://localhost:3000. Click "Start Meeting" — redirects to `/m/[uuid]`. The Start button on the footer requires real env vars; expect mic permission prompt + immediate connection-error if no AssemblyAI key set. That's correct behavior pre-deploy. Ctrl+C to stop.

- [ ] **Step 4: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/app/m
git commit -m "feat(live-nexus): active meeting SPA wiring (Task 19)"
```

---

## Task 20: E2E test with mocked services (Playwright)

**Files:**
- Create: `live-nexus/playwright.config.ts`
- Create: `live-nexus/e2e/start-end-meeting.spec.ts`

- [ ] **Step 1: Install browsers**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm exec playwright install chromium
```

- [ ] **Step 2: Playwright config**

`live-nexus/playwright.config.ts`:
```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://localhost:3000", trace: "on-first-retry" },
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      ASSEMBLYAI_API_KEY: "fake_key_for_e2e",
      ANTHROPIC_API_KEY: "fake_key_for_e2e",
      DRIVE_SERVICE_ACCOUNT_JSON: "{}",
      DRIVE_FOLDER_ID: "fake_folder",
    },
  },
});
```

- [ ] **Step 3: Write E2E test**

`live-nexus/e2e/start-end-meeting.spec.ts`:
```typescript
import { test, expect } from "@playwright/test";

test("landing page renders brand chrome and preflight", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("UNITE GROUP NEXUS")).toBeVisible();
  await expect(page.getByText("Live meeting notes")).toBeVisible();
  await expect(page.getByText(/microphone/i)).toBeVisible();
});

test("start button redirects to /m/[uuid]", async ({ page, context }) => {
  await context.grantPermissions(["microphone"]);
  // Stub /api/session to return ok so preflight passes
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 200, body: JSON.stringify({ token: "x", ws_url: "wss://x", expires_at: Date.now() + 60000 }) })
  );
  await page.goto("/");
  // Wait for preflight to pass
  await page.waitForTimeout(500);
  const startButton = page.locator("button:has-text('Start Meeting')");
  await expect(startButton).toBeEnabled({ timeout: 5000 });
  await startButton.click();
  await expect(page).toHaveURL(/\/m\/[\w-]+/);
  await expect(page.getByText("UNITE GROUP NEXUS")).toBeVisible();
});
```

- [ ] **Step 4: Run E2E**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm e2e
```
Expected: 2 passed (with browser launching).

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/playwright.config.ts live-nexus/e2e live-nexus/package.json live-nexus/pnpm-lock.yaml
git commit -m "test(live-nexus): Playwright E2E for landing + start (Task 20)"
```

---

## Task 21: Deploy to Vercel

**Files:** none (Vercel dashboard)

- [ ] **Step 1: Push branch to GitHub**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git push
```

- [ ] **Step 2: Create Vercel project**

Go to https://vercel.com/new. Import `CleanExpo/Pi-Dev-Ops` repo. In project settings:
- **Root directory:** `live-nexus`
- **Framework preset:** Next.js (auto-detected)
- **Build command:** `pnpm build`
- **Install command:** `pnpm install`

- [ ] **Step 3: Set environment variables**

In Vercel project settings → Environment Variables, add for **Production**:
- `ASSEMBLYAI_API_KEY` = (from Task 0 step 1)
- `ANTHROPIC_API_KEY` = (working key from `~/.hermes/.env`, currently the swapped KEY_3 value)
- `DRIVE_SERVICE_ACCOUNT_JSON` = (paste the FULL JSON from Task 0 step 2 — the entire service-account key file as a single line)
- `DRIVE_FOLDER_ID` = (from Task 0 step 3)

Hit Save. Trigger a redeploy.

- [ ] **Step 4: Configure custom domain**

Vercel project → Settings → Domains → Add `live.unite-group.in`. Vercel shows a DNS record to add — copy it.

Open your DNS provider (Cloudflare / Namecheap / etc.), navigate to `unite-group.in`'s DNS records, add the CNAME or A record Vercel asked for. Wait ~2 minutes for propagation.

- [ ] **Step 5: Smoke test the deployed URL**

Open `https://live.unite-group.in` in Chrome. Verify:
- Page loads with Unite-Group brand chrome
- Preflight check shows ✓ for microphone (after granting permission), ✓ for network, ✓ for browser
- Click Start Meeting → redirects to `/m/[uuid]`
- Header shows LIVE dot pulsing Candy Red
- Speak — transcript appears word-by-word within 1-2s
- Wait 30s — sidebar populates with topics
- Click End Meeting → "Open in Drive" CTA appears
- Click Open in Drive → opens the saved markdown file in Google Drive

- [ ] **Step 6: No commit (deployment is dashboard-driven)**

---

## Task 22: Live integration test (opt-in)

**Files:**
- Create: `live-nexus/tests/live-meeting.live.test.ts`

- [ ] **Step 1: Write the live test**

`live-nexus/tests/live-meeting.live.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { mintServiceAccountToken, createDriveFile } from "@/lib/drive-client";

const RUN_LIVE = process.env.RUN_LIVE_NEXUS === "1";

describe.skipIf(!RUN_LIVE)("live integration", () => {
  it("AssemblyAI: mints a token via /api/session shape", async () => {
    const apiKey = process.env.ASSEMBLYAI_API_KEY;
    if (!apiKey) throw new Error("ASSEMBLYAI_API_KEY not set");
    const res = await fetch("https://api.assemblyai.com/v2/realtime/token", {
      method: "POST",
      headers: { Authorization: apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({ expires_in: 60 }),
    });
    expect(res.ok).toBe(true);
    const data = (await res.json()) as { token: string };
    expect(typeof data.token).toBe("string");
    expect(data.token.length).toBeGreaterThan(10);
  });

  it("Anthropic: tool_use returns valid update_synthesis", async () => {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({
        model: "claude-haiku-4-5",
        max_tokens: 256,
        system: "Reply only via the test_tool tool.",
        messages: [{ role: "user", content: "Just call the tool with topics=['ok'] and actions=[]" }],
        tools: [{
          name: "test_tool",
          description: "test",
          input_schema: { type: "object", properties: { topics: { type: "array", items: { type: "string" } }, actions: { type: "array", items: {} } }, required: ["topics", "actions"] },
        }],
        tool_choice: { type: "tool", name: "test_tool" },
      }),
    });
    expect(res.ok).toBe(true);
  });

  it("Drive: service-account creates and reads a probe file", async () => {
    const saJson = process.env.DRIVE_SERVICE_ACCOUNT_JSON;
    const folderId = process.env.DRIVE_FOLDER_ID;
    if (!saJson || !folderId) throw new Error("Drive env vars not set");
    const token = await mintServiceAccountToken(JSON.parse(saJson));
    const result = await createDriveFile({
      accessToken: token,
      folderId,
      filename: `probe-${Date.now()}.md`,
      content: "# probe\n\nlive-test, please delete",
      mimeType: "text/markdown",
    });
    expect(result.fileId).toBeTruthy();
    expect(result.webViewLink).toContain("drive.google.com");
    console.log("Created probe file:", result.webViewLink);
    console.log("REMINDER: delete this file in Drive when convenient.");
  });
});
```

- [ ] **Step 2: Verify unit suite still passes (live tests skipped)**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus && pnpm test
```
Expected: all unit + the 3 live tests skipped.

- [ ] **Step 3: Run live tests (env vars must be set)**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops/live-nexus
RUN_LIVE_NEXUS=1 \
  ASSEMBLYAI_API_KEY=$(grep '^ASSEMBLYAI_API_KEY=' ~/.hermes/.env | cut -d= -f2-) \
  ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ~/.hermes/.env | cut -d= -f2-) \
  DRIVE_SERVICE_ACCOUNT_JSON="$(cat /path/to/service-account.json)" \
  DRIVE_FOLDER_ID="<folder-id-from-task-0>" \
  pnpm test live-meeting
```
Expected: 3 passed. Test creates ONE probe file in Drive; remember to delete it.

- [ ] **Step 4: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add live-nexus/tests/live-meeting.live.test.ts
git commit -m "test(live-nexus): live integration test gated by RUN_LIVE_NEXUS=1 (Task 22)"
```

---

## Post-implementation acceptance checklist

After all tasks merged:

- [ ] `https://live.unite-group.in` loads with Unite-Group brand chrome
- [ ] Pre-flight tech check passes within 2s
- [ ] Click Start → mic permission → AssemblyAI streaming within 3s
- [ ] Transcript renders word-by-word, no flicker
- [ ] Sidebar updates every 30s with Topics + Action Items
- [ ] Click End → save within 5s → "Open in Drive" link works
- [ ] Saved markdown matches spec format (frontmatter + 3 sections)
- [ ] WiFi-drop test: Reconnecting banner <2s, recovery <3s
- [ ] Anthropic-fail test: synthesis-paused pill, transcript unaffected
- [ ] Tab close + reopen <10min → state restored

When all checked, sub-project 3 is shipped.
