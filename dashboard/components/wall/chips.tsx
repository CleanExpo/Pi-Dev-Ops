// Shared chip colours for the Live Wall. GREEN only when an outside source says so.
import type { Chip } from "@/lib/wall/snapshot";

export const CHIP_BG: Record<Chip, string> = {
  GREEN: "#15803d",
  RED: "#b91c1c",
  GREY: "#4b5563",
};

export function ChipBadge({ chip, label }: { chip: Chip; label?: string }) {
  return (
    <span
      data-chip={chip}
      className="inline-block rounded px-2 py-0.5 text-sm font-semibold tracking-wide"
      style={{ background: CHIP_BG[chip], color: "#fff" }}
    >
      {label ?? chip}
    </span>
  );
}

export function fmtAge(seconds: number | null): string {
  if (seconds === null) return "age unknown";
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}
