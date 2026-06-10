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
  branch: "pidev/launch-crew-wirein",
  commit: "verified tailnet bridge",
  prUrl: "https://github.com/CleanExpo/Pi-Dev-Ops/compare/main...pidev/launch-crew-wirein",
  testsCommand: "cd D:\\Pi-Dev-Ops; python -m pytest tests/test_analyst.py tests/test_wiki_sync.py -q",
  testsExpected: "11 passed",
  headline: "Mac Mini brain host is live. Next: wire env vars into Railway / Margot.",
  explanation:
    "Margot was calling analyst.py after every research turn, but the file did not exist — " +
    "research never compounded into wiki notes. That runtime is now wired. The vault lives on " +
    "the Mac Mini, not this Windows PC.",
  milestones: [
    {
      id: "pc",
      title: "Windows PC — code",
      status: "done",
      summary: "Analyst, wiki_sync, aip_watcher, MCP read, 11 tests green, committed.",
    },
    {
      id: "github",
      title: "GitHub — branch pushed",
      status: "done",
      summary: "Branch pidev/launch-crew-wirein is on origin. Merge PR when ready.",
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
      title: "Windows PC (phill-desktop)",
      status: "next",
      summary: "Online on tailnet 100.94.139.34 · set OBSIDIAN_REMOTE_URL to verified Mac Mini FQDN",
    },
  ],
  checklist: [
    {
      id: "verify-pc",
      label: "Verify on Windows PC",
      status: "next",
      detail: "Run pytest — expect 12 passed.",
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
      id: "mac-env",
      label: "Mac Mini: set env vars (Railway / Margot)",
      status: "next",
      detail: "Use the verified FQDN plus tailnet IP fallback. Only OBSIDIAN_TOKEN and Supabase service key need secret handling.",
      commands: [
        'export BRAIN1_WIKI_DIR="$HOME/2nd Brain/2nd Brain/Wiki"',
        'export OBSIDIAN_VAULT="$HOME/2nd Brain/2nd Brain"',
        'export OBSIDIAN_TOKEN="<paste-from-obsidian-plugin>"',
        'export BRAIN_HOST_TAILNET="unite-mac-mini.tail5ef339.ts.net"',
        'export OBSIDIAN_REMOTE_URL="https://unite-mac-mini.tail5ef339.ts.net:27124"',
        'export OBSIDIAN_REMOTE_IP="100.107.147.59"',
        'export SUPABASE_UNITE_GROUP_URL="https://lksfwktwtmyznckodsau.supabase.co"',
        'export SUPABASE_UNITE_GROUP_SERVICE_KEY="<service-role-key>"',
      ],
    },
    {
      id: "mac-clone",
      label: "Mac Mini: get latest code (script is on feature branch)",
      status: "next",
      detail: "setup-brain-host.sh is NOT on main yet. Clone/checkout the feature branch OR use commands above.",
      commands: [
        "git clone https://github.com/CleanExpo/Pi-Dev-Ops.git",
        "cd Pi-Dev-Ops",
        "git fetch origin pidev/launch-crew-wirein",
        "git checkout pidev/launch-crew-wirein",
        "bash scripts/setup-brain-host.sh",
      ],
    },
    {
      id: "win-remote",
      label: "Windows PC (phill-desktop): remote vault access",
      status: "next",
      detail: "phill-desktop is already on the tailnet. Use the verified FQDN plus IP fallback:",
      commands: [
        '$env:OBSIDIAN_REMOTE_URL="https://unite-mac-mini.tail5ef339.ts.net:27124"',
        '$env:OBSIDIAN_REMOTE_IP="100.107.147.59"',
        '$env:OBSIDIAN_TOKEN="<same-key-as-mac-mini>"',
        '$env:BRAIN_HOST_TAILNET="unite-mac-mini.tail5ef339.ts.net"',
      ],
    },
  ],
};
