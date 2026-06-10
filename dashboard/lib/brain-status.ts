/** Single source of truth for 2nd Brain flywheel UI — update when milestones change. */

export type BrainItemStatus = "done" | "blocked" | "next" | "waiting";

export interface BrainChecklistItem {
  id: string;
  label: string;
  status: BrainItemStatus;
  detail?: string;
  commands?: string[];
}

export interface BrainMilestone {
  id: string;
  title: string;
  status: BrainItemStatus;
  summary: string;
}

export interface BrainStatusSnapshot {
  title: string;
  updated: string;
  branch: string;
  commit: string;
  prUrl: string;
  testsCommand: string;
  testsExpected: string;
  headline: string;
  explanation: string;
  milestones: BrainMilestone[];
  checklist: BrainChecklistItem[];
}

export const BRAIN_STATUS: BrainStatusSnapshot = {
  title: "2nd Brain Flywheel",
  updated: "2026-06-10",
  branch: "main",
  commit: "9b5cdf1",
  prUrl: "https://github.com/CleanExpo/Pi-Dev-Ops/pulls?q=319+320+321+322+323+324",
  testsCommand: "python -m pytest tests/test_analyst.py tests/test_margot_research_voice.py tests/test_margot_tools_gemini.py tests/test_obsidian_analyst_relay.py tests/test_wiki_sync.py -q",
  testsExpected: "Main CI, Smoke Test, pgtap, Codebase Wiki, and DESIGN lint green at 9b5cdf1",
  headline: "Production Brain write/read and Margot quick research fallback are proven.",
  explanation:
    "The deployed Margot path writes analyst deliverables into the Mac Mini Obsidian vault through a narrow relay. " +
    "Proof turn mt-c0902995e4 ran direct [RESEARCH], used the Gemini quick fallback without margot_unreachable, " +
    "completed analyst ingest, and wrote Wiki/analyst/2026-06-10-what-is-the-nature-origin-and-content-of-the-art.md. " +
    "Remaining future work is full corpus-backed Margot MCP packaging, not the quick research/write path.",
  milestones: [
    {
      id: "pc",
      title: "Windows PC — code",
      status: "done",
      summary: "Analyst, wiki_sync, aip_watcher, MCP read, Margot Gemini fallback, and focused pytest checks are green.",
    },
    {
      id: "github",
      title: "GitHub — merged to main",
      status: "done",
      summary: "PRs #310-#324 merged, Codebase Wiki green, and main CI/smoke green at 9b5cdf1.",
    },
    {
      id: "mac",
      title: "Mac Mini — brain host (unite-mac-mini)",
      status: "done",
      summary: "Tailscale ✓ Obsidian REST ✓ Serve bridge ✓ https://unite-mac-mini.tail5ef339.ts.net:27124",
    },
    {
      id: "mbp",
      title: "MacBook Pro (phills-macbook-pro)",
      status: "waiting",
      summary: "Online on tailnet 100.103.191.107 · Obsidian vault sync when ready",
    },
    {
      id: "pc-net",
      title: "Production path — Brain write/read",
      status: "done",
      summary: "Done — production turn mt-ec68962ee6 wrote and read back the Mac Mini analyst note.",
    },
  ],
  checklist: [
    {
      id: "verify-pc",
      label: "Verify local analyst tests",
      status: "done",
      detail: "Done — expect 12 passed if rerun.",
      commands: [
        "cd D:\\Pi-Dev-Ops",
        "python -m pytest tests/test_analyst.py tests/test_wiki_sync.py -q",
      ],
    },
    {
      id: "mac-tailscale",
      label: "Mac Mini: Tailscale",
      status: "done",
      detail: "Done — unite-mac-mini · 100.107.147.59",
      commands: ["tailscale status  # unite-mac-mini is online"],
    },
    {
      id: "mac-obsidian",
      label: "Mac Mini: Obsidian REST API",
      status: "done",
      detail: "Done — Local REST API with MCP enabled. HTTPS and local HTTP endpoints are active; token stays local.",
      commands: [
        "tailscale serve status",
        "curl -k https://127.0.0.1:27124/",
      ],
    },
    {
      id: "mac-serve",
      label: "Mac Mini: Tailscale Serve bridge",
      status: "done",
      detail: "Done — tailnet HTTPS terminates at Tailscale Serve and proxies to Obsidian local HTTP.",
      commands: [
        "tailscale serve --bg --https=27124 http://127.0.0.1:27123",
        "tailscale serve status",
      ],
    },
    {
      id: "mac-relay",
      label: "Mac Mini: production analyst relay",
      status: "done",
      detail: "Done — narrow relay accepts only authenticated Wiki/analyst writes and is exposed through Tailscale Funnel on allowed public port 10000.",
      commands: [
        'security add-generic-password -a "$USER" -s pi-ceo-obsidian-token -w "<paste-token>" -U',
        "cp scripts/launchd/com.piceo.obsidian-analyst-relay.plist ~/Library/LaunchAgents/",
        'launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.piceo.obsidian-analyst-relay.plist',
        "tailscale funnel --bg --https=10000 http://127.0.0.1:27125",
        "curl -4 -k https://unite-mac-mini.tail5ef339.ts.net:10000/health",
      ],
    },
    {
      id: "mac-env",
      label: "Railway / Margot env vars",
      status: "done",
      detail: "Done — production uses the Funnel relay URL plus public IPv4 fallback. Tokens stay redacted.",
      commands: [
        'export BRAIN1_WIKI_DIR="$HOME/2nd Brain/2nd Brain/Wiki"',
        'export OBSIDIAN_VAULT="$HOME/2nd Brain/2nd Brain"',
        'export OBSIDIAN_TOKEN="<paste-from-obsidian-plugin>"',
        'export BRAIN_HOST_TAILNET="unite-mac-mini.tail5ef339.ts.net"',
        'export OBSIDIAN_REMOTE_URL="https://unite-mac-mini.tail5ef339.ts.net:10000"',
        'export OBSIDIAN_REMOTE_IP="43.245.48.174"',
        'export SUPABASE_UNITE_GROUP_URL="https://lksfwktwtmyznckodsau.supabase.co"',
        'export SUPABASE_UNITE_GROUP_SERVICE_KEY="<service-role-key>"',
      ],
    },
    {
      id: "mac-clone",
      label: "Mac Mini: get latest code",
      status: "done",
      detail: "Done — setup-brain-host.sh is now on main via PR #310.",
      commands: [
        "git clone https://github.com/CleanExpo/Pi-Dev-Ops.git",
        "cd Pi-Dev-Ops",
        "git checkout main",
        "bash scripts/setup-brain-host.sh",
      ],
    },
    {
      id: "live-brain-proof",
      label: "Live Brain proof",
      status: "done",
      detail: "Done — production turn mt-ec68962ee6 wrote and read Wiki/analyst/2026-06-10-what-does-the-evidence-say-about-brain-host-live.md.",
      commands: [
        "curl -sS https://pi-dev-ops-production.up.railway.app/health",
        'rg -n "mt-ec68962ee6" "$HOME/2nd Brain/2nd Brain/Wiki/analyst/2026-06-10-what-does-the-evidence-say-about-brain-host-live.md"',
      ],
    },
    {
      id: "research-bridge",
      label: "Margot quick research bridge",
      status: "done",
      detail: "Done — production proof mt-c0902995e4 returned HTTP 200, research_called=true, no margot_unreachable, analyst+ingest complete, and Obsidian relay PUT 204.",
      commands: [
        'railway logs --lines 1000 | rg -i "mt-c0902995e4|analyst\\+ingest|margot_unreachable|timeout"',
        'rg -n "mt-c0902995e4|brain-analyst-json-proof-20260610094815" "$HOME/2nd Brain/2nd Brain/Wiki/analyst"',
      ],
    },
    {
      id: "corpus-mcp",
      label: "Next: full corpus-backed Margot MCP",
      status: "next",
      detail: "Gemini quick research is live. Full private-corpus MCP packaging remains the next upgrade if Margot must use the private File Search corpus from Railway.",
      commands: [
        'railway logs --lines 300 | rg -i "corpus|margot-deep-research|MARGOT_FILE_SEARCH_STORE"',
        "# Package the Margot MCP server into the Railway image before enabling corpus-backed deep research.",
      ],
    },
  ],
};
