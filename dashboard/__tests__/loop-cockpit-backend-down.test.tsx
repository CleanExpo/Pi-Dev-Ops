// Loop Cockpit — a dead backend must never render as a healthy loop.
//
// The defect this pins:
//
//   The page already has a `disconnected` guard, and a comment saying
//   "Absent data must NOT read as 'healthy'". It could never fire.
//
//   `getJSON` gives up only on `!res.ok`. But when the Pi-CEO backend is
//   unreachable the proxy does not return an error — `quietFallback` in
//   app/api/pi-ceo/[...path]/route.ts returns **HTTP 200** with a placeholder
//   body, stamped `X-Upstream-Status: 502`. So all four fetches "succeed",
//   `disconnected` (which needs all four to be null) stays false, `needs` is
//   empty because the placeholders contain nothing, and the cockpit prints
//   "Nothing needs you — the loop is healthy" at a system that is entirely down.
//
//   The honest signal was already being sent and nobody read it.
//
// Why the existing loop-cockpit-observability test never caught it: it mocks
// the non-mission-control endpoints as 404, which is a shape the real proxy
// never produces. This test reproduces what the proxy ACTUALLY sends.
//
// Written to FAIL against the pre-fix page.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import LoopCockpit from "@/app/(main)/loop/page";

const HEALTHY_TEXT = /Nothing needs you/;
const DISCONNECTED_TEXT = /Disconnected/;

/**
 * The page renders "Disconnected" on its FIRST frame, before any fetch has
 * resolved — all four state slots start null. Asserting straight after render
 * therefore passes no matter what the fetches return, which is how the first
 * draft of this test went green against the unfixed page.
 *
 * `synced —` is the loading marker in the header; `refresh()` replaces it with
 * a clock time. Waiting for that flip is what makes every assertion below an
 * assertion about POST-fetch state.
 */
async function settle() {
  const synced = await screen.findByText(/^synced/);
  await waitFor(() => expect(synced.textContent).not.toMatch(/—/));
}

/**
 * Every endpoint answered exactly as `quietFallback` answers it when the
 * backend is unreachable: status 200, X-Upstream-Status 502, placeholder body.
 * Bodies copied from route.ts so the fixture cannot drift into fiction.
 */
function mockProxyFallback() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const error = "Pi CEO server unreachable or wrong password";
      const headers = { "Content-Type": "application/json", "X-Upstream-Status": "502" };

      let body: unknown = { error };
      if (url.includes("/api/mission-control/live")) {
        body = {
          ts: new Date().toISOString(),
          throughput: { hourly: Array.from({ length: 24 }, () => 0) },
          active_sessions: [],
          recent_completions: [],
          queue: { urgent: 0, high: 0, next_issue_id: null, next_issue_title: error },
          pulse: { last_at: null, comments_today: 0, pulse_issue_id: null },
          observability: {
            source: "proxy_fallback",
            ok: false,
            fully_observed: false,
            red_components: ["pi_ceo_backend"],
            degraded_components: [],
            actions: [],
          },
          error,
        };
      } else if (url.includes("/api/routines")) {
        body = { runs: [], total: 0, error };
      }

      // The defect in one line: status 200, not an error status.
      return new Response(JSON.stringify(body), { status: 200, headers });
    }),
  );
}

/** Control: a genuinely healthy backend, so the assertions below can't pass vacuously. */
function mockHealthyBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      let body: unknown = {};
      if (url.includes("/api/autonomy/status")) {
        body = { enabled: true, linear_api_key: true };
      } else if (url.includes("/api/mission-control/live")) {
        body = {
          ts: new Date().toISOString(),
          throughput: { hourly: Array.from({ length: 24 }, () => 0) },
          active_sessions: [],
          recent_completions: [],
          queue: { urgent: 0, high: 0, next_issue_id: null },
          pulse: { last_at: null, comments_today: 0, pulse_issue_id: null },
          observability: {
            ok: true,
            fully_observed: true,
            red_components: [],
            degraded_components: [],
            actions: [],
          },
        };
      } else if (url.includes("/api/routines")) {
        body = { runs: [], total: 0 };
      }
      // No X-Upstream-Status header — this is what the proxy's success path returns.
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

describe("Loop Cockpit — backend unreachable behind a 200-returning proxy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  describe("when the proxy is serving fallbacks", () => {
    beforeEach(mockProxyFallback);

    it("does NOT claim the loop is healthy", async () => {
      render(<LoopCockpit />);
      await settle();
      expect(screen.queryByText(HEALTHY_TEXT)).toBeNull();
    });

    it("tells the founder the backend is unreachable", async () => {
      render(<LoopCockpit />);
      await settle();
      const msg = screen.getByText(DISCONNECTED_TEXT);
      expect(msg.textContent).toMatch(/unreachable|not authenticated/i);
    });

    it("does not invent a CAUSE it cannot know", async () => {
      // The placeholder body is `{error: "..."}`. `enabled` is absent, so
      // `!autonomy.enabled` is true and the cockpit announces
      // "Autonomy poller is disabled (TAO_AUTONOMY_ENABLED=0)" — naming a
      // specific env var as the reason. Nothing is known about the poller;
      // the backend never answered. A fabricated cause is worse than silence
      // because the founder can act on it.
      render(<LoopCockpit />);
      await settle();
      expect(screen.queryByText(/TAO_AUTONOMY_ENABLED=0/)).toBeNull();
    });

    it("does not render undefined placeholder values as data", async () => {
      render(<LoopCockpit />);
      await settle();
      expect(document.body.textContent).not.toMatch(/undefined/);
    });
  });

  describe("control — a genuinely healthy backend", () => {
    beforeEach(mockHealthyBackend);

    it("still reports healthy, so the fix cannot be 'always say disconnected'", async () => {
      render(<LoopCockpit />);
      await settle();
      expect(screen.getByText(HEALTHY_TEXT)).toBeTruthy();
      expect(screen.queryByText(DISCONNECTED_TEXT)).toBeNull();
    });
  });
});
