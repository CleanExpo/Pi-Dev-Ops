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
    <aside
      className="w-[200px] min-h-screen flex flex-col shrink-0 relative"
      style={{
        background: "linear-gradient(180deg, #0F0F0F 0%, #0A0A0A 100%)",
        borderRight: "1px solid rgba(232,117,26,0.15)",
      }}
    >
      {/* Orange top accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent, #E8751A, transparent)",
        }}
      />

      {/* Logo */}
      <div className="px-5 pt-6 pb-5 border-b border-white/5">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span
            className="font-bebas text-xl leading-none"
            style={{ color: "#E8751A" }}
          >
            π
          </span>
          <span className="font-bebas text-xl tracking-[0.12em] text-white leading-none">
            i CEO
          </span>
        </div>
        <p className="font-mono text-[9px] text-white/30 tracking-widest uppercase pl-1">
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
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-150 group"
              style={
                active
                  ? {
                      background: "rgba(232,117,26,0.12)",
                      color: "#E8751A",
                      border: "1px solid rgba(232,117,26,0.2)",
                    }
                  : {
                      color: "rgba(255,255,255,0.4)",
                      border: "1px solid transparent",
                    }
              }
            >
              <span
                className="text-xs"
                style={{ color: active ? "#E8751A" : "rgba(255,255,255,0.25)" }}
              >
                {icon}
              </span>
              {label}
            </a>
          );
        })}
      </nav>

      {/* Status + logout */}
      <div className="px-4 py-4 border-t border-white/5">
        <div className="flex items-center gap-2 mb-3">
          <span
            className="w-1.5 h-1.5 rounded-full status-dot-active"
            style={{ backgroundColor: "#4CAF82" }}
          />
          <span className="font-mono text-[9px] text-white/30 uppercase tracking-wider">
            Backend Live
          </span>
        </div>
        <button
          onClick={logout}
          disabled={loggingOut}
          className="w-full text-left px-3 py-1.5 text-xs font-mono rounded-lg transition-all duration-150 disabled:opacity-40"
          style={{ color: "rgba(255,255,255,0.3)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#EF4444";
            e.currentTarget.style.background = "rgba(239,68,68,0.06)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "rgba(255,255,255,0.3)";
            e.currentTarget.style.background = "transparent";
          }}
        >
          {loggingOut ? "Logging out…" : "← Log out"}
        </button>
      </div>
    </aside>
  );
}
