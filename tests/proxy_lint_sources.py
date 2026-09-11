"""Source fixtures for the Pi-CEO proxy fallback gate tests.

Extracted from `test_proxy_fallback_lint.py` so that file stays under the
300-line convention. These are inputs only — every assertion about them lives
in the test module.
"""

# A client that renders whatever the proxy hands it. The defect.
BLIND_SOURCE = """
async function load() {
  const res = await fetch(`/api/pi-ceo/api/autonomy/status`);
  if (!res.ok) return null;
  return await res.json();
}
"""

# The same client, routed through the honest reader.
HONEST_SOURCE = """
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
async function load() {
  return await fetchProxyJSON("/api/autonomy/status");
}
"""

# Touches the proxy path only in a comment; still a consumer by the textual
# rule, and deliberately so — the gate says it is textual rather than pretending
# to understand the code.
NON_CONSUMER_SOURCE = """
export const POLL_MS = 20_000;
"""


# ── The three shapes that made an earlier version of this gate blind ────────
# It required a literal `fetch(` within 120 chars of the URL. These three are
# all real files in this repo, and all three were silently dropped — the count
# fell 18 -> 14 and read as a cleaner result. Each is now a control.

CONST_URL_SOURCE = """
const API = "/api/pi-ceo/api/margot/assets";
async function load() {
  const res = await fetch(API);
  return await res.json();
}
"""

WRAPPER_HELPER_SOURCE = """
async function fetchJson<T>(u: string): Promise<T | null> {
  const r = await fetch(u);
  return r.ok ? await r.json() : null;
}
const j = await fetchJson<SessionsResp>("/api/pi-ceo/api/terminal/sessions");
"""

COMMENT_ONLY_SOURCE = """
// Read-only. Polls /api/pi-ceo/api/terminal/sessions every 5s.
export const POLL_MS = 5000;
"""

POST_ONLY_SOURCE = """
async function file() {
  const res = await fetch("/api/pi-ceo/api/goal-ticket", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal: "x" }),
  });
  return res.ok;
}
"""

SSE_SOURCE = """
function openStream(sid: string) {
  const es = new EventSource(`/api/pi-ceo/api/sessions/${sid}/logs`);
  return es;
}
"""



