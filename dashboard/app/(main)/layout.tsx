// app/(main)/layout.tsx — shared nav layout for dashboard, chat, history
"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import ThemeToggle from "@/components/ThemeToggle";

const NAV = [
  { href: "/dashboard", label: "DASHBOARD", icon: "⊞" },
  { href: "/builds",    label: "BUILDS",    icon: "⚙" },
  { href: "/chat",      label: "CHAT",      icon: "◈" },
  { href: "/history",   label: "HISTORY",   icon: "☰" },
  { href: "/settings",  label: "SETTINGS",  icon: "⊙" },
];

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "var(--c-bg)", color: "var(--c-text)" }}>

      {/* ── Top nav — hidden on mobile, visible sm+ ───────────────── */}
      <nav
        className="hidden sm:flex items-center justify-between px-4 h-11 shrink-0"
        style={{ borderBottom: "1px solid var(--c-border)", background: "var(--c-bg)" }}
      >
        <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity shrink-0">
          <span className="font-mono text-sm" style={{ color: "var(--c-orange)" }}>π</span>
          <span className="font-display text-base tracking-widest" style={{ color: "var(--c-text)" }}>PI CEO</span>
          <span className="font-mono text-[10px] ml-2 hidden lg:block" style={{ color: "var(--c-chrome)" }}>
            AUTONOMOUS DEV PLATFORM
          </span>
        </Link>
        <div className="flex items-center">
          {NAV.map(({ href, label }) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className="font-mono text-xs px-3 py-1 transition-colors min-h-[44px] flex items-center"
                style={{
                  borderLeft: "1px solid var(--c-border)",
                  color: active ? "var(--c-orange)" : "var(--c-muted)",
                }}
              >
                {label}
              </Link>
            );
          })}
          <ThemeToggle />
        </div>
      </nav>

      {/* ── Mobile top bar — logo + theme toggle only ─────────────── */}
      <div
        className="flex sm:hidden items-center justify-between px-4 h-11 shrink-0"
        style={{ borderBottom: "1px solid var(--c-border)", background: "var(--c-bg)" }}
      >
        <Link href="/" className="flex items-center gap-2">
          <span className="font-mono text-sm" style={{ color: "var(--c-orange)" }}>π</span>
          <span className="font-display text-base tracking-widest" style={{ color: "var(--c-text)" }}>PI CEO</span>
        </Link>
        <ThemeToggle />
      </div>

      {/* ── Page content ──────────────────────────────────────────── */}
      {/* On mobile, add bottom padding so content doesn't sit under the tab bar */}
      <div className="flex-1 flex flex-col pb-16 sm:pb-0">{children}</div>

      {/* ── Mobile bottom tab bar — visible only on mobile ────────── */}
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
                background: active ? "var(--c-panel)" : "transparent",
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
