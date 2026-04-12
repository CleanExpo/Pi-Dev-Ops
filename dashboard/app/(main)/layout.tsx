// app/(main)/layout.tsx — cinematic app shell
// Design bridge: carries the landing page's Bloomberg terminal aesthetic (Bebas Neue
// wordmark, orange π accent, warm-dark glow) into every interior page so the user
// never feels they've left the same visual world.
"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import ThemeToggle from "@/components/ThemeToggle";

const NAV = [
  { href: "/dashboard", label: "DASHBOARD",  icon: "⊞", key: "dashboard" },
  { href: "/builds",    label: "BUILDS",     icon: "⚙", key: "builds"    },
  { href: "/chat",      label: "CHAT",       icon: "◈", key: "chat"      },
  { href: "/history",   label: "HISTORY",    icon: "☰", key: "history"   },
  { href: "/settings",  label: "SETTINGS",   icon: "⊙", key: "settings"  },
];

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div
      className="flex flex-col min-h-screen"
      style={{
        /* Ambient warm glow in top-left — subtle reference to landing hero warmth */
        background: "radial-gradient(ellipse at 0% 0%, rgba(232,117,26,0.04) 0%, transparent 45%), var(--c-bg)",
        color: "var(--c-text)",
      }}
    >

      {/* ══════════════════════════════════════════════════════════════
          TOP NAV — desktop (sm+)
          Design: cinematic header with orange accent underline,
          Bebas Neue wordmark matching the landing page exactly.
      ══════════════════════════════════════════════════════════════ */}
      <nav
        className="hidden sm:flex items-stretch justify-between h-12 shrink-0 relative"
        style={{
          background: "linear-gradient(to bottom, rgba(232,117,26,0.03) 0%, transparent 100%), var(--c-bg)",
          borderBottom: "1px solid var(--c-border)",
        }}
      >
        {/* Thin orange accent line at very bottom of nav */}
        <div
          aria-hidden
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: "1px",
            background: "linear-gradient(to right, var(--c-orange) 0%, rgba(232,117,26,0.2) 35%, transparent 60%)",
            zIndex: 1,
          }}
        />

        {/* ── Logo wordmark ── */}
        <Link
          href="/"
          className="flex items-center gap-2 px-5 hover:opacity-80 transition-opacity shrink-0 group"
          style={{ borderRight: "1px solid var(--c-border)" }}
        >
          {/* Large orange π — same as landing page */}
          <span
            className="font-mono leading-none group-hover:animate-pulse-orange"
            style={{ color: "var(--c-orange)", fontSize: "16px", letterSpacing: "0.15em" }}
          >
            π
          </span>
          {/* PI CEO in Bebas Neue — same typeface as the landing hero */}
          <span
            className="font-display leading-none tracking-widest"
            style={{ fontSize: "20px", color: "var(--c-text)", letterSpacing: "0.12em" }}
          >
            PI CEO
          </span>
          {/* Tagline — hidden on smaller desktop */}
          <span
            className="font-mono hidden lg:block ml-1"
            style={{ fontSize: "9px", color: "var(--c-chrome)", letterSpacing: "0.2em" }}
          >
            AUTONOMOUS DEV PLATFORM
          </span>
        </Link>

        {/* ── Navigation links ── */}
        <div className="flex items-stretch">
          {NAV.map(({ href, label }) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className="flex items-center px-4 font-mono text-xs tracking-widest transition-colors relative"
                style={{
                  borderLeft: "1px solid var(--c-border)",
                  color: active ? "var(--c-orange)" : "var(--c-chrome)",
                  background: active ? "rgba(232,117,26,0.04)" : "transparent",
                  minHeight: "100%",
                }}
              >
                {active && (
                  /* Active indicator: orange top border (same aesthetic as bottom tab bar) */
                  <span
                    aria-hidden
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      right: 0,
                      height: "2px",
                      background: "var(--c-orange)",
                    }}
                  />
                )}
                {label}
              </Link>
            );
          })}

          {/* ── Theme toggle ── */}
          <div
            className="flex items-center px-3"
            style={{ borderLeft: "1px solid var(--c-border)" }}
          >
            <ThemeToggle />
          </div>
        </div>
      </nav>

      {/* ══════════════════════════════════════════════════════════════
          MOBILE TOP BAR — logo + theme toggle only
      ══════════════════════════════════════════════════════════════ */}
      <div
        className="flex sm:hidden items-center justify-between px-4 h-12 shrink-0 relative"
        style={{
          background: "linear-gradient(to bottom, rgba(232,117,26,0.03) 0%, transparent 100%), var(--c-bg)",
          borderBottom: "1px solid var(--c-border)",
        }}
      >
        {/* Orange accent line */}
        <div
          aria-hidden
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: "1px",
            background: "linear-gradient(to right, var(--c-orange) 0%, rgba(232,117,26,0.15) 40%, transparent 65%)",
          }}
        />

        <Link href="/" className="flex items-center gap-2">
          <span className="font-mono" style={{ color: "var(--c-orange)", fontSize: "15px", letterSpacing: "0.15em" }}>π</span>
          <span className="font-display leading-none" style={{ fontSize: "18px", color: "var(--c-text)", letterSpacing: "0.12em" }}>PI CEO</span>
        </Link>
        <ThemeToggle />
      </div>

      {/* ══════════════════════════════════════════════════════════════
          PAGE CONTENT
          Ambient background continues from the nav through the full page.
      ══════════════════════════════════════════════════════════════ */}
      <div className="flex-1 flex flex-col pb-16 sm:pb-0">
        {children}
      </div>

      {/* ══════════════════════════════════════════════════════════════
          MOBILE BOTTOM TAB BAR
      ══════════════════════════════════════════════════════════════ */}
      <nav
        className="fixed bottom-0 left-0 right-0 sm:hidden flex z-50 h-16"
        style={{
          borderTop: "1px solid var(--c-border)",
          background: "var(--c-bg)",
        }}
      >
        {NAV.map(({ href, label, icon }) => {
          const active = path === href;
          return (
            <Link
              key={href}
              href={href}
              className="flex-1 flex flex-col items-center justify-center gap-0.5 transition-colors"
              style={{
                color: active ? "var(--c-orange)" : "var(--c-chrome)",
                borderTop: active ? "2px solid var(--c-orange)" : "2px solid transparent",
                background: active ? "rgba(232,117,26,0.04)" : "transparent",
              }}
            >
              <span className="text-base leading-none">{icon}</span>
              <span className="font-mono text-[9px] tracking-wider">{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
