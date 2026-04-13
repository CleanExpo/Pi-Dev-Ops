/**
 * analyze-utils.test.ts — Unit tests for lib/analyze-utils.ts
 *
 * Tests the three pure utility functions extracted from app/api/analyze/route.ts:
 * - buildLessonsSummary: parses lessons.jsonl, sorts by severity, trims to topN
 * - sanitizeRepoUrl: normalises github.com URLs, rejects non-GitHub URLs
 * - sseEncode: produces correctly-framed SSE bytes
 */
import { describe, it, expect } from "vitest";
import {
  buildLessonsSummary,
  sanitizeRepoUrl,
  sseEncode,
} from "@/lib/analyze-utils";

// ── buildLessonsSummary ────────────────────────────────────────────────────

describe("buildLessonsSummary", () => {
  it("returns empty string for blank input", () => {
    expect(buildLessonsSummary("")).toBe("");
    expect(buildLessonsSummary("   \n  ")).toBe("");
  });

  it("returns empty string when no records have a lesson field", () => {
    const raw = JSON.stringify({ severity: "error", source: "ci" }) + "\n";
    expect(buildLessonsSummary(raw)).toBe("");
  });

  it("includes header and footer in output", () => {
    const raw = JSON.stringify({ severity: "info", source: "ci", lesson: "Always pin deps" });
    const out = buildLessonsSummary(raw);
    expect(out).toContain("LESSONS FROM PRIOR RUNS");
    expect(out).toContain("=================================================================");
  });

  it("formats each lesson as [severity][source] lesson", () => {
    const raw = JSON.stringify({ severity: "warn", source: "deploy", lesson: "Check env vars" });
    const out = buildLessonsSummary(raw);
    expect(out).toContain("[warn][deploy] Check env vars");
  });

  it("uses 'info' and '?' as fallbacks for missing severity / source", () => {
    const raw = JSON.stringify({ lesson: "Bare minimum lesson" });
    const out = buildLessonsSummary(raw);
    expect(out).toContain("[info][?] Bare minimum lesson");
  });

  it("sorts error before warn before info", () => {
    const lines = [
      JSON.stringify({ severity: "info",  source: "a", lesson: "Info lesson" }),
      JSON.stringify({ severity: "error", source: "b", lesson: "Error lesson" }),
      JSON.stringify({ severity: "warn",  source: "c", lesson: "Warn lesson" }),
    ].join("\n");
    const out = buildLessonsSummary(lines);
    const errorIdx = out.indexOf("Error lesson");
    const warnIdx  = out.indexOf("Warn lesson");
    const infoIdx  = out.indexOf("Info lesson");
    expect(errorIdx).toBeLessThan(warnIdx);
    expect(warnIdx).toBeLessThan(infoIdx);
  });

  it("respects topN limit", () => {
    const lines = Array.from({ length: 10 }, (_, i) =>
      JSON.stringify({ severity: "info", source: "s", lesson: `Lesson ${i}` })
    ).join("\n");
    const out = buildLessonsSummary(lines, 3);
    const matches = out.match(/\[info\]/g) ?? [];
    expect(matches.length).toBe(3);
  });

  it("skips malformed JSON lines silently", () => {
    const raw = [
      "not json at all",
      JSON.stringify({ severity: "error", source: "ci", lesson: "Valid lesson" }),
      "{broken",
    ].join("\n");
    const out = buildLessonsSummary(raw);
    expect(out).toContain("Valid lesson");
  });
});

// ── sanitizeRepoUrl ────────────────────────────────────────────────────────

describe("sanitizeRepoUrl", () => {
  it("accepts a plain https://github.com URL", () => {
    expect(sanitizeRepoUrl("https://github.com/owner/repo"))
      .toBe("https://github.com/owner/repo");
  });

  it("prepends https:// when scheme is missing", () => {
    expect(sanitizeRepoUrl("github.com/owner/repo"))
      .toBe("https://github.com/owner/repo");
  });

  it("normalises http:// to https://", () => {
    expect(sanitizeRepoUrl("http://github.com/owner/repo"))
      .toBe("https://github.com/owner/repo");
  });

  it("strips www. prefix", () => {
    expect(sanitizeRepoUrl("https://www.github.com/owner/repo"))
      .toBe("https://github.com/owner/repo");
  });

  it("trims surrounding whitespace", () => {
    expect(sanitizeRepoUrl("  https://github.com/owner/repo  "))
      .toBe("https://github.com/owner/repo");
  });

  it("throws for non-GitHub URLs", () => {
    expect(() => sanitizeRepoUrl("https://gitlab.com/owner/repo"))
      .toThrow("Invalid GitHub repository URL");
  });

  it("throws for empty string", () => {
    expect(() => sanitizeRepoUrl("")).toThrow("Invalid GitHub repository URL");
  });

  it("throws for github.com URL missing the /owner/repo path", () => {
    expect(() => sanitizeRepoUrl("https://github.com/")).toThrow();
  });
});

// ── sseEncode ─────────────────────────────────────────────────────────────

describe("sseEncode", () => {
  const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

  it("produces a frame starting with 'event: <name>'", () => {
    const frame = decode(sseEncode("line", { text: "hi" }));
    expect(frame.startsWith("event: line\n")).toBe(true);
  });

  it("includes 'data: <json>' on the second line", () => {
    const frame = decode(sseEncode("done", { ok: true }));
    expect(frame).toContain('\ndata: {"ok":true}\n');
  });

  it("ends with a double newline (SSE frame terminator)", () => {
    const frame = decode(sseEncode("ping", {}));
    expect(frame.endsWith("\n\n")).toBe(true);
  });

  it("serialises nested objects correctly", () => {
    const data = { type: "error", text: "something failed", ts: 1234567890.1 };
    const frame = decode(sseEncode("line", data));
    expect(frame).toContain(JSON.stringify(data));
  });
});
