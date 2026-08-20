"use client";

import Link from "next/link";
import { CONTROL_SECTIONS } from "@/lib/control/nav";

export default function ControlHubTiles() {
  return (
    <section aria-label="Control sections">
      <h2
        className="text-[10px] font-semibold uppercase tracking-widest mb-2"
        style={{ color: "var(--text-muted)" }}
      >
        Sections
      </h2>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {CONTROL_SECTIONS.map((item, index) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="block rounded-md px-3 py-3 h-full transition-colors"
              style={{
                background: "var(--panel)",
                border: `1px solid ${index === 0 ? "var(--accent)" : "var(--border)"}`,
              }}
            >
              <span className="text-sm font-medium" style={{ color: "var(--text)" }}>
                {item.title}
              </span>
              <span className="block text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
                {item.blurb}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
