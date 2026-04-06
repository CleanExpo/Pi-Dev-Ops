// app/page.tsx — full-screen cinematic landing page
import Link from "next/link";

export default function LandingPage() {
  return (
    <div
      className="fixed inset-0 flex flex-col items-center justify-center"
      style={{
        backgroundImage: "url(/pi-ceo-hero.jpg)",
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
      }}
    >
      {/* Dark overlay */}
      <div
        className="absolute inset-0"
        style={{ background: "linear-gradient(to bottom, rgba(10,10,10,0.55) 0%, rgba(10,10,10,0.75) 60%, rgba(10,10,10,0.92) 100%)" }}
      />

      {/* Content */}
      <div className="relative flex flex-col items-center text-center px-6">
        {/* Pi symbol */}
        <span
          className="font-mono mb-3 tracking-widest"
          style={{ color: "#E8751A", fontSize: "18px", letterSpacing: "0.4em" }}
        >
          π
        </span>

        {/* Main title */}
        <h1
          className="font-display leading-none"
          style={{
            fontSize: "clamp(72px, 14vw, 160px)",
            color: "#F0EDE8",
            letterSpacing: "0.06em",
            textShadow: "0 2px 40px rgba(0,0,0,0.8)",
          }}
        >
          PI CEO
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontFamily: "'Barlow', sans-serif",
            fontWeight: 600,
            fontSize: "clamp(14px, 2.5vw, 22px)",
            color: "#F0EDE8",
            letterSpacing: "0.35em",
            marginTop: "8px",
            textTransform: "uppercase",
            opacity: 0.9,
          }}
        >
          Solo DevOps Tool
        </p>

        {/* Powered by */}
        <p
          className="font-mono mt-3"
          style={{
            fontSize: "10px",
            color: "#E8751A",
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            opacity: 0.85,
          }}
        >
          Powered by Claude Harness
        </p>

        {/* CTA */}
        <Link
          href="/dashboard"
          className="mt-12 font-mono font-bold tracking-widest transition-opacity hover:opacity-80"
          style={{
            background: "#E8751A",
            color: "#FFFFFF",
            padding: "14px 56px",
            fontSize: "13px",
            letterSpacing: "0.25em",
          }}
        >
          ENTER ↗
        </Link>

        {/* Build info */}
        <p
          className="font-mono mt-8"
          style={{ fontSize: "9px", color: "#F0EDE8", opacity: 0.35, letterSpacing: "0.2em" }}
        >
          8 ANALYSIS PHASES · CLAUDE OPUS 4.6 · TAO FRAMEWORK
        </p>
      </div>
    </div>
  );
}
