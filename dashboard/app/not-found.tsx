// app/not-found.tsx — 404 page
import Link from "next/link";
import { CSS } from "@/lib/brand-tokens";

export default function NotFound() {
  return (
    <div
      className="dark flex flex-col items-center justify-center min-h-screen font-mono"
      style={{ background: "var(--background)", color: "var(--text)" }}
    >
      <div className="text-center px-8">
        <div className="mb-2 text-[48px] font-bold" style={{ color: CSS.accent, fontFamily: "'Bebas Neue', sans-serif" }}>
          404
        </div>
        <p className="text-[11px] uppercase tracking-widest mb-6" style={{ color: "var(--text-dim)" }}>
          Page Not Found
        </p>
        <p className="text-[10px] mb-8" style={{ color: "var(--text-muted)" }}>
          The requested route does not exist in Pi CEO.
        </p>
        <Link
          href="/control"
          className="font-mono text-[11px] px-6 py-2 tracking-wider"
          style={{ background: CSS.accent, color: CSS.onAccent, fontWeight: 700 }}
        >
          ← CONTROL
        </Link>
      </div>
    </div>
  );
}
