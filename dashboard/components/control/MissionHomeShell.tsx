import Link from "next/link";
import type { ReactNode } from "react";
import MargotBubble from "@/components/margot/MargotBubble";
import { MISSION_HOME_LINKS } from "@/lib/control/mission-home-links";
import styles from "./mission-home-shell.module.css";

export default function MissionHomeShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Mission Control navigation">
        <Link href="/control" className={styles.identity}>
          <span className={styles.mark}>π</span>
          <span><strong>Pi Dev Ops</strong><small>Mission Control</small></span>
        </Link>
        <nav className={styles.nav} aria-label="Mission Control views">
          {MISSION_HOME_LINKS.map((item) => (
            <Link key={item.href} href={item.href} aria-current={item.href === "/control" ? "page" : undefined}>
              <span aria-hidden="true">{item.symbol}</span>{item.label}
            </Link>
          ))}
        </nav>
        <p className={styles.footer}>Status comes from observed sources. Unknown stays unknown.</p>
      </aside>
      {/* data-mc-page: page content without the aside nav (e2e-live check 5). */}
      <main data-mc-page="" className={styles.main}>
        {children}
        <MargotBubble className={styles.margot} />
      </main>
    </div>
  );
}
