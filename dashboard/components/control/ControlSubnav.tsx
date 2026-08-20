"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CONTROL_NAV } from "@/lib/control/nav";
import { controlTabActive } from "@/lib/nav-active";

export default function ControlSubnav() {
  const path = usePathname();

  return (
    <nav
      aria-label="Control sections"
      className="flex items-center gap-1 px-3 overflow-x-auto shrink-0"
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--background)",
      }}
    >
      {CONTROL_NAV.map((item) => {
        const active = controlTabActive(path, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="shrink-0 px-2.5 py-2 text-[10px] font-mono uppercase tracking-widest"
            style={{
              color: active ? "var(--accent)" : "var(--text-muted)",
              borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
            }}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
