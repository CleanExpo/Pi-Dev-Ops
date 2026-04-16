// app/not-found.tsx — 404 page
import Link from "next/link";

export default function NotFound() {
  return (
    <div
      className="flex flex-col items-center justify-center min-h-screen font-mono"
      style={{ background: "#0A0A0A", color: "#F0EDE8" }}
    >
      <div className="text-center px-8">
        <div className="mb-2 text-[48px] font-bold" style={{ color: "#E8751A", fontFamily: "'Bebas Neue', sans-serif" }}>
          404
        </div>
        <p className="text-[11px] uppercase tracking-widest mb-6" style={{ color: "#888480" }}>
          Page Not Found
        </p>
        <p className="text-[10px] mb-8" style={{ color: "#C8C5C0" }}>
          The requested route does not exist in Pi CEO.
        </p>
        <Link
          href="/control"
          className="font-mono text-[11px] px-6 py-2 tracking-wider"
          style={{ background: "#E8751A", color: "#FFF", fontWeight: 700 }}
        >
          ← CONTROL
        </Link>
      </div>
    </div>
  );
}
