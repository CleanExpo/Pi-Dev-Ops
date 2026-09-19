// Persistent failure banner — outside the accordion, never collapsed, never hidden.
// Renders even at zero so "no banner" can never be mistaken for "no problems".
import { CHIP_BG } from "./chips";

export function WallBanner({ red, grey, staleAge }: { red: number; grey: number; staleAge: number | null | "missing" }) {
  return (
    <div className="flex flex-col gap-2" data-testid="wall-banner">
      {staleAge !== null && (
        <div
          role="alert"
          data-testid="wall-stale"
          className="w-full rounded-md px-6 py-4 text-3xl font-bold"
          style={{ background: CHIP_BG.GREY, color: "#fff" }}
        >
          SNAPSHOT STALE — {staleAge === "missing" ? "no timestamp" : `age ${staleAge}s`}
        </div>
      )}
      <div className="flex items-center gap-6 text-3xl font-bold" style={{ color: "#f3f4f6" }}>
        <span data-testid="banner-red" style={{ color: red > 0 ? "#f87171" : "#9ca3af" }}>RED {red}</span>
        <span aria-hidden>·</span>
        <span data-testid="banner-grey" style={{ color: grey > 0 ? "#d1d5db" : "#9ca3af" }}>GREY {grey}</span>
      </div>
    </div>
  );
}
