import Link from "next/link";
import type { ReactNode } from "react";
import MargotBubble from "@/components/margot/MargotBubble";
import styles from "./mission-home-shell.module.css";

const LINKS = [
  { href: "/control", label: "Mission Control", symbol: "⌂" },
  { href: "/projects", label: "Portfolio", symbol: "◇" },
  { href: "/control/build", label: "Work", symbol: "☷" },
  { href: "/control/health", label: "Evidence", symbol: "▤" },
  { href: "/command-centre/wall", label: "Machines", symbol: "▣" },
];

export default function MissionHomeShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Mission Control navigation">
        <Link href="/control" className={styles.identity}>
          <span className={styles.mark}>π</span>
          <span><strong>Pi Dev Ops</strong><small>Mission Control</small></span>
        </Link>
        <nav className={styles.nav} aria-label="Mission Control views">
          {LINKS.map((item) => (
            <Link key={item.href} href={item.href} aria-current={item.href === "/control" ? "page" : undefined}>
              <span aria-hidden="true">{item.symbol}</span>{item.label}
            </Link>
          ))}
        </nav>
        <p className={styles.footer}>Status comes from observed sources. Unknown stays unknown.</p>
      </aside>
      <main className={styles.main}>
        {children}
        <MargotBubble className={styles.margot} />
      </main>
    </div>
  );
}
