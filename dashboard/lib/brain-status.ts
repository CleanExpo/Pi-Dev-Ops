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
  commit: "e808d6b",
  prUrl: "https://github.com/CleanExpo/Pi-Dev-Ops/pull/310",
  testsCommand: "cd D:\\Pi-Dev-Ops; python -m pytest tests/test_analyst.py tests/test_wiki_sync.py -q",
  testsExpected: "12 passed; main CI green",
  headline: "Brain host code is merged. Next: prove one live production Brain write/read.",
  explanation:
    "Margot was calling analyst.py after every research turn, but the file did not exist. " +
    "That runtime, the persistent Brain page, and the tailnet Obsidian bridge setup are now on main. " +
    "The remaining gate is operational proof from the deployed path into the Mac Mini vault.",
  milestones: [
    {
      id: "pc",
      title: "Windows PC — code",
      status: "done",
      summary: "Analyst, wiki_sync, aip_watcher, MCP read, and 12 focused pytest checks are green.",
    },
    {
      id: "github",
      title: "GitHub — merged to main",
      status: "done",
      summary: "PR #310 merged, follow-up CI fixes merged, and main is green at e808d6b.",
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
      status: "next",
      summary: "Run one deployed Margot/analyst turn and verify the resulting Obsidian note is readable.",
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
      id: "mac-env",
      label: "Railway / Margot env vars",
      status: "done",
      detail: "Done — verified FQDN plus tailnet IP fallback were set in Railway. Tokens stay redacted.",
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
      label: "Next: live Brain proof",
      status: "next",
      detail: "Run a real deployed Margot/analyst turn, then read back the Obsidian note from the Mac Mini vault.",
      commands: [
        "curl -sS https://pi-dev-ops-production.up.railway.app/health",
        "open https://dashboard-unite-group.vercel.app/brain",
        "# Trigger one Margot/analyst research turn, then verify Wiki/analyst/<new-note>.md exists in Obsidian.",
      ],
    },
  ],
};
