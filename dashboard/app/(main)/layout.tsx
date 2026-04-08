// app/(main)/layout.tsx — shared nav layout for dashboard, chat, history
"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";

const NAV = [
  { href: "/dashboard", label: "DASHBOARD" },
  { href: "/builds",    label: "BUILDS" },
  { href: "/chat",      label: "CHAT" },
  { href: "/history",   label: "HISTORY" },
  { href: "/settings",  label: "SETTINGS" },
];

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div className="flex flex-col min-h-screen bg-bg text-text">
      {/* Nav */}
      <nav
        className="flex items-center justify-between px-4 h-10 shrink-0"
        style={{ borderBottom: "1px solid #2A2727", background: "#0A0A0A" }}
      >
        <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
          <span className="font-mono text-[11px]" style={{ color: "#E8751A" }}>π</span>
          <span className="font-display text-base tracking-widest" style={{ color: "#F0EDE8" }}>PI CEO</span>
          <span className="font-mono text-[9px] ml-2 hidden sm:block" style={{ color: "#888480" }}>
            AUTONOMOUS DEV PLATFORM
          </span>
        </Link>
        <div className="flex items-center gap-1">
          {NAV.map(({ href, label }) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className="font-mono text-[10px] px-3 py-1 transition-colors"
                style={{
                  borderLeft: "1px solid #2A2727",
                  color: active ? "#E8751A" : "#C8C5C0",
                }}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </nav>
      <div className="flex-1 flex flex-col">{children}</div>
    </div>
  );
}
