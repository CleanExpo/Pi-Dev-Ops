// app/layout.tsx — root layout with nav bar
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pi CEO — Autonomous Dev Platform",
  description: "GitHub repo analysis engine powered by Claude + TAO framework",
};

const NAV = [
  { href: "/",        label: "DASHBOARD" },
  { href: "/chat",    label: "CHAT" },
  { href: "/history", label: "HISTORY" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bg text-text font-body min-h-screen flex flex-col">
        {/* Nav */}
        <nav
          className="flex items-center justify-between px-4 h-10 shrink-0"
          style={{ borderBottom: "1px solid #252525", background: "#0A0A0A" }}
        >
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-orange">π</span>
            <span className="font-display text-base tracking-widest text-text">PI CEO</span>
            <span className="font-mono text-[9px] text-[#777] ml-2 hidden sm:block">
              AUTONOMOUS DEV PLATFORM
            </span>
          </div>
          <div className="flex items-center gap-1">
            {NAV.map(({ href, label }) => (
              <a
                key={href}
                href={href}
                className="font-mono text-[10px] px-3 py-1 text-[#999] hover:text-text transition-colors"
                style={{ borderLeft: "1px solid #252525" }}
              >
                {label}
              </a>
            ))}
          </div>
        </nav>
        <div className="flex-1 flex flex-col">{children}</div>
      </body>
    </html>
  );
}
