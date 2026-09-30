/**
 * RA-7846 — which secret the dashboard attaches to the fleet read.
 *
 * The read-only key wins so the write-capable shared secret never has to live
 * on the dashboard host; the shared ones remain as fallbacks so an existing
 * deployment keeps working.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { meshSecret } from "@/lib/control/mesh-upstream";

const KEYS = ["TAO_FLEET_READ_SECRET", "TAO_INTERNAL_WEBHOOK_SECRET", "TAO_WEBHOOK_SECRET"] as const;

function setEnv(values: Partial<Record<(typeof KEYS)[number], string>>): void {
  for (const key of KEYS) vi.stubEnv(key, values[key] ?? "");
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("meshSecret", () => {
  it("prefers the read-only key over the shared secrets", () => {
    setEnv({ TAO_FLEET_READ_SECRET: "read", TAO_INTERNAL_WEBHOOK_SECRET: "int", TAO_WEBHOOK_SECRET: "hook" });
    expect(meshSecret()).toBe("read");
  });

  it("falls back to the internal secret, then the webhook secret", () => {
    setEnv({ TAO_INTERNAL_WEBHOOK_SECRET: "int", TAO_WEBHOOK_SECRET: "hook" });
    expect(meshSecret()).toBe("int");
    setEnv({ TAO_WEBHOOK_SECRET: "hook" });
    expect(meshSecret()).toBe("hook");
  });

  it("trims whitespace and returns empty when nothing is set", () => {
    setEnv({ TAO_FLEET_READ_SECRET: "  read \n" });
    expect(meshSecret()).toBe("read");
    setEnv({});
    expect(meshSecret()).toBe("");
  });
});
