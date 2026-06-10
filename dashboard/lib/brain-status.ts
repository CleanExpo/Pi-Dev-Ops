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
  commit: "ba41b3a",
  prUrl: "https://github.com/CleanExpo/Pi-Dev-Ops/compare/main...pidev/launch-crew-wirein",
  testsCommand: "cd D:\\Pi-Dev-Ops; python -m pytest tests/test_analyst.py tests/test_wiki_sync.py -q",
  testsExpected: "11 passed",
  headline: "Tailscale is live on Mac Mini (unite-mac-mini). Next: Obsidian REST + env vars.",
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
      status: "next",
      summary: "Tailscale ✓ 100.107.147.59 · Next: Obsidian REST plugin + env vars",
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
      status: "waiting",
      summary: "Online on tailnet 100.94.139.34 · set OBSIDIAN_REMOTE_URL to Mac Mini",
    },
  ],
  checklist: [
    {
      id: "verify-pc",
      label: "Verify on Windows PC",
      status: "next",
      detail: "Run pytest — expect 11 passed.",
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
      status: "next",
      detail: "Obsidian → Settings → Community plugins → Local REST API → Enable. Copy API key.",
      commands: [],
    },
    {
      id: "mac-env",
      label: "Mac Mini: set env vars (Railway / Margot)",
      status: "next",
      detail: "Your Mac Mini hostname is unite-mac-mini. Only OBSIDIAN_TOKEN and Supabase key need pasting.",
      commands: [
        'export BRAIN1_WIKI_DIR="$HOME/2nd Brain/2nd Brain/Wiki"',
        'export OBSIDIAN_VAULT="$HOME/2nd Brain/2nd Brain"',
        'export OBSIDIAN_TOKEN="<paste-from-obsidian-plugin>"',
        'export BRAIN_HOST_TAILNET="unite-mac-mini"',
        'export OBSIDIAN_REMOTE_URL="https://unite-mac-mini:27124"',
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
      status: "waiting",
      detail: "phill-desktop is already on the tailnet. Install Tailscale app on Windows if not linked, then:",
      commands: [
        '$env:OBSIDIAN_REMOTE_URL="https://unite-mac-mini:27124"',
        '$env:OBSIDIAN_TOKEN="<same-key-as-mac-mini>"',
        '$env:BRAIN_HOST_TAILNET="unite-mac-mini"',
      ],
    },
  ],
};
