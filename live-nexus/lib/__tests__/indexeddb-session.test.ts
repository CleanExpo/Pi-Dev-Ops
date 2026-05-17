import { describe, it, expect, beforeEach } from "vitest";
import {
  saveSession,
  loadSession,
  clearSession,
  hasFreshSession,
} from "../indexeddb-session";

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
