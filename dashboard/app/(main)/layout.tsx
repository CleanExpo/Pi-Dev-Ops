// app/(main)/layout.tsx — sidebar nav shell (Linear/Vercel aesthetic)
"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import ThemeToggle from "@/components/ThemeToggle";
import CeoHealthPanel from "@/components/CeoHealthPanel";
import { useEffect, useState } from "react";

const NAV = [
  { href: "/overview",  label: "Overview",  icon: "◈", key: "overview"  },
  { href: "/dashboard", label: "Analysis",  icon: "⊞", key: "dashboard" },
  { href: "/builds",    label: "Builds",    icon: "⚙", key: "builds"   },
  { href: "/routines",  label: "Routines",  icon: "↻", key: "routines"  },
  { href: "/projects",  label: "Portfolio", icon: "◫", key: "projects"  },
  { href: "/chat",      label: "Chat",      icon: "◉", key: "chat"     },
  { href: "/history",   label: "History",   icon: "☰", key: "history"  },
  { href: "/settings",  label: "Settings",  icon: "⊙", key: "settings" },
];

interface HealthData {
  swarm_enabled: boolean;
  swarm_shadow: boolean;
}

function SwarmStatus() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const res = await fetch("/api/pi-ceo/api/health");
        if (res.ok) {
          const data = await res.json() as HealthData;
          setHealth(data);
        } else {
          setHealth(null);
        }
      } catch {
        setHealth(null);
      } finally {
        setLoading(false);
      }
    }

    void fetchHealth();
    const t = setInterval(() => { void fetchHealth(); }, 60_000);
    return () => clearInterval(t);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--text-dim)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Connecting…</span>
      </div>
    );
  }

  if (!health || !health.swarm_enabled) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--error)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Swarm Off</span>
      </div>
    );
  }

  if (health.swarm_shadow) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--warning)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Swarm Shadow</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--success)" }} />
      <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Swarm Active</span>
    </div>
  );
}

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div className="flex min-h-screen bg-background text-text">

      {/* ══════════════════════════════════════════════════════════════
          SIDEBAR — icon-only at sm (48px), full at lg (220px)
      ══════════════════════════════════════════════════════════════ */}
      <aside
        className="hidden sm:flex flex-col shrink-0 h-screen sticky top-0 w-12 lg:w-[220px]"
        style={{
          background: "var(--panel)",
          borderRight: "1px solid var(--border)",
        }}
      >
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center justify-center lg:justify-start gap-2.5 px-0 lg:px-4 h-[52px] shrink-0 hover:opacity-80 transition-opacity"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <span
            className="font-mono leading-none"
            style={{ color: "var(--accent)", fontSize: "18px" }}
          >
            π
          </span>
          <div className="hidden lg:flex flex-col gap-0">
            <span className="text-sm font-semibold leading-tight" style={{ color: "var(--text)" }}>
              Pi CEO
            </span>
            <span
              className="uppercase tracking-wider leading-none"
              style={{ fontSize: "10px", color: "var(--text-dim)" }}
            >
              Autonomous
            </span>
          </div>
        </Link>

        {/* Nav links */}
        <nav className="flex flex-col gap-0.5 px-2 py-3 flex-1">
          {NAV.map(({ href, label, icon }) => {
            const active = path === href || (href !== "/dashboard" && path.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                title={label}
                className="flex items-center justify-center lg:justify-start gap-2.5 px-0 lg:px-3 h-9 text-sm font-medium rounded-md transition-colors"
                style={{
                  color:      active ? "var(--accent)"      : "var(--text-muted)",
                  background: active ? "var(--accent-subtle)" : "transparent",
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLAnchorElement).style.color = "var(--text)";
                    (e.currentTarget as HTMLAnchorElement).style.background = "var(--panel-hover)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-muted)";
                    (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
                  }
                }}
              >
                <span className="text-base leading-none w-4 text-center shrink-0">{icon}</span>
                <span className="hidden lg:inline">{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer: CEO health panel + theme toggle */}
        <CeoHealthPanel />
        <div
          className="flex items-center justify-end px-4 py-2 shrink-0"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <ThemeToggle />
        </div>
      </aside>

      {/* ══════════════════════════════════════════════════════════════
          MOBILE TOP BAR — logo + theme toggle only
      ══════════════════════════════════════════════════════════════ */}
      <div
        className="sm:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 h-[52px] shrink-0"
        style={{
          background: "var(--panel)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Link href="/" className="flex items-center gap-2">
          <span className="font-mono" style={{ color: "var(--accent)", fontSize: "16px" }}>π</span>
          <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>Pi CEO</span>
        </Link>
        <ThemeToggle />
      </div>

      {/* ══════════════════════════════════════════════════════════════
          PAGE CONTENT
      ══════════════════════════════════════════════════════════════ */}
      <div className="flex-1 flex flex-col min-w-0 sm:mt-0 mt-[52px] pb-16 sm:pb-0">
        {children}
      </div>

      {/* ══════════════════════════════════════════════════════════════
          MOBILE BOTTOM TAB BAR — 5 items
      ══════════════════════════════════════════════════════════════ */}
      <nav
        className="fixed bottom-0 left-0 right-0 sm:hidden flex z-50 h-16"
        style={{
          background: "var(--panel)",
          borderTop: "1px solid var(--border)",
        }}
      >
        {NAV.map(({ href, label, icon }) => {
          const active = path === href || (href !== "/dashboard" && path.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className="flex-1 flex flex-col items-center justify-center gap-0.5 transition-colors"
              style={{
                color:       active ? "var(--accent)" : "var(--text-dim)",
                borderTop:   active ? "2px solid var(--accent)" : "2px solid transparent",
                background:  active ? "var(--accent-subtle)" : "transparent",
              }}
            >
              <span className="text-base leading-none">{icon}</span>
              <span className="text-[9px] font-medium tracking-wide leading-tight">{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
