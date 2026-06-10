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
  commit: "e7ad3f0",
  prUrl: "https://github.com/CleanExpo/Pi-Dev-Ops/compare/main...pidev/launch-crew-wirein",
  testsCommand: "cd D:\\Pi-Dev-Ops; python -m pytest tests/test_analyst.py tests/test_wiki_sync.py -q",
  testsExpected: "11 passed",
  headline: "PC code is done and tested. Brain host setup is on the Mac Mini.",
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
      title: "Mac Mini — brain host",
      status: "next",
      summary: "Tailscale + Obsidian REST + env vars. Vault path: ~/2nd Brain/2nd Brain",
    },
    {
      id: "mbp",
      title: "MacBook Pro — mobile",
      status: "waiting",
      summary: "Tailscale + Obsidian vault sync to reach Mac Mini.",
    },
    {
      id: "pc-net",
      title: "Windows PC — network",
      status: "waiting",
      summary: "Tailscale + OBSIDIAN_REMOTE_URL pointing at Mac Mini.",
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
      status: "next",
      detail: "Install and sign in. Copy your machine's Tailscale DNS name.",
      commands: [
        "brew install tailscale",
        "sudo tailscale up",
        "tailscale ip -4",
        "tailscale status",
      ],
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
      detail: "Replace placeholders. TS_NAME = your Mac's Tailscale name.",
      commands: [
        'export BRAIN1_WIKI_DIR="$HOME/2nd Brain/2nd Brain/Wiki"',
        'export OBSIDIAN_VAULT="$HOME/2nd Brain/2nd Brain"',
        'export OBSIDIAN_TOKEN="<paste-from-obsidian-plugin>"',
        'export BRAIN_HOST_TAILNET="<your-mac-tailscale-name>"',
        'export OBSIDIAN_REMOTE_URL="https://<your-mac-tailscale-name>:27124"',
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
      label: "Windows PC: remote vault access",
      status: "waiting",
      commands: [
        "# After Tailscale on Windows:",
        '$env:OBSIDIAN_REMOTE_URL="https://<mac-mini-tailscale-name>:27124"',
        '$env:OBSIDIAN_TOKEN="<same-key-as-mac>"',
      ],
    },
  ],
};
