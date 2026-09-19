/**
 * Live Wall browser rules and render (docs/briefs/live-wall-v1.md §5-6): a stale or
 * stampless snapshot greys everything; rotation never skips a GREY station; the
 * banner renders at zero; colour survives collapse.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StationAccordion } from "@/components/wall/StationAccordion";
import { WallBanner } from "@/components/wall/WallBanner";
import {
  displayChip, isSnapshotStale, nextStation, resolveKioskMachine, rotationOrder, STALE_AFTER_MS,
} from "@/lib/wall/client";
import type { Station } from "@/lib/wall/snapshot";

const NOW = Date.parse("2026-09-19T00:00:00Z");
const st = (id: string, chip: Station["chip"]): Station => ({ id, name: id, chip, reason: `${id} reason` });

describe("snapshot freshness", () => {
  it("a fresh stamp is not stale (positive control)", () => {
    expect(isSnapshotStale(new Date(NOW - 1000).toISOString(), NOW)).toBe(false);
  });
  it.each([undefined, null, "", "garbage"])("stamp %j is stale", (v) => {
    expect(isSnapshotStale(v, NOW)).toBe(true);
  });
  it("older than three polls is stale, and staleness greys a GREEN chip", () => {
    expect(isSnapshotStale(new Date(NOW - STALE_AFTER_MS - 1).toISOString(), NOW)).toBe(true);
    expect(displayChip("GREEN", true)).toBe("GREY");
    expect(displayChip("GREEN", false)).toBe("GREEN");
  });
});

describe("rotation", () => {
  it("covers every non-GREEN station, RED first, and never skips an all-GREY station", () => {
    const order = rotationOrder([st("a", "GREEN"), st("b", "GREY"), st("c", "RED"), st("d", "GREY")]);
    expect(order).toEqual(["c", "b", "d"]);
  });
  it("rotates everything when all are GREEN, and wraps", () => {
    expect(rotationOrder([st("a", "GREEN"), st("b", "GREEN")])).toEqual(["a", "b"]);
    expect(nextStation(["a", "b"], "b")).toBe("a");
    expect(nextStation(["a", "b"], null)).toBe("a");
  });
});

describe("kiosk machine", () => {
  it("matches case-insensitively and flags an unknown host", () => {
    expect(resolveKioskMachine("phill_desktop", ["Phill_Desktop"])).toEqual({ host: "Phill_Desktop", unknown: false });
    expect(resolveKioskMachine("nope", ["Phill_Desktop"])).toEqual({ host: null, unknown: true });
    expect(resolveKioskMachine(null, ["Phill_Desktop"])).toEqual({ host: null, unknown: false });
  });
});

describe("render", () => {
  it("banner renders at zero", () => {
    render(<WallBanner red={0} grey={0} staleAge={null} />);
    expect(screen.getByTestId("banner-red").textContent).toBe("RED 0");
    expect(screen.getByTestId("banner-grey").textContent).toBe("GREY 0");
    expect(screen.queryByTestId("wall-stale")).toBeNull();
  });
  it("stale banner names the age", () => {
    render(<WallBanner red={0} grey={2} staleAge={42} />);
    expect(screen.getByTestId("wall-stale").textContent).toContain("age 42s");
  });
  it("a collapsed station keeps its colour; a stale wall greys a GREEN station", () => {
    const { rerender } = render(<StationAccordion stations={[st("x", "RED"), st("y", "GREEN")]} open={null} stale={false} onPick={() => {}} />);
    expect(screen.getByTestId("station-x").dataset.chip).toBe("RED");
    expect(screen.queryByText("x reason")).toBeNull();
    rerender(<StationAccordion stations={[st("x", "RED"), st("y", "GREEN")]} open={null} stale onPick={() => {}} />);
    expect(screen.getByTestId("station-y").dataset.chip).toBe("GREY");
  });
});
