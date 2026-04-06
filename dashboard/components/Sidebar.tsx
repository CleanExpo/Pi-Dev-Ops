"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";

const NAV = [
  { label: "Dashboard", href: "/dashboard", icon: "◈" },
  { label: "Build", href: "/dashboard#build", icon: "⚡" },
  { label: "Terminal", href: "/dashboard#terminal", icon: "▶" },
  { label: "Files", href: "/dashboard#files", icon: "◻" },
  { label: "Skills", href: "/dashboard#skills", icon: "◆" },
];

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const [loggingOut, setLoggingOut] = useState(false);

  async function logout() {
    setLoggingOut(true);
    await api.logout().catch(() => {});
    router.replace("/");
  }

  return (
    <aside className="w-[200px] min-h-screen bg-pi-dark-2 border-r border-pi-border flex flex-col shrink-0">
      {/* Logo */}
      <div className="px-5 py-6 border-b border-pi-border">
        <div className="flex items-center gap-2">
          <span className="w-1 h-6 bg-pi-orange rounded-sm" />
          <span className="font-bebas text-2xl tracking-[0.15em] text-pi-cream">
            PI CEO
          </span>
        </div>
        <p className="font-mono text-[9px] text-pi-muted mt-0.5 pl-3 tracking-widest uppercase">
          Solo DevOps
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ label, href, icon }) => {
          const active =
            href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(href.split("#")[0]);
          return (
            <a
              key={label}
              href={href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-all duration-150 group ${
                active
                  ? "bg-pi-orange/10 text-pi-orange border border-pi-orange/20"
                  : "text-pi-muted hover:text-pi-cream hover:bg-pi-dark-3"
              }`}
            >
              <span
                className={`text-xs ${active ? "text-pi-orange" : "text-pi-muted group-hover:text-pi-cream"}`}
              >
                {icon}
              </span>
              {label}
            </a>
          );
        })}
      </nav>

      {/* Status badge */}
      <div className="px-4 py-3 border-t border-pi-border">
        <div className="flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 status-dot-active" />
          <span className="font-mono text-[9px] text-pi-muted uppercase tracking-wider">
            Backend Live
          </span>
        </div>
        <button
          onClick={logout}
          disabled={loggingOut}
          className="w-full text-left px-3 py-1.5 text-xs font-mono text-pi-muted hover:text-red-400 hover:bg-red-400/5 rounded transition-all duration-150 disabled:opacity-40"
        >
          {loggingOut ? "Logging out…" : "← Log out"}
        </button>
      </div>
    </aside>
  );
}
