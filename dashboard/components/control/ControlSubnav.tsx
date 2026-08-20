"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CONTROL_NAV } from "@/lib/control/nav";
import { controlTabActive } from "@/lib/nav-active";
import styles from "./control-deck.module.css";

export default function ControlSubnav() {
  const path = usePathname();

  return (
    <nav className={styles.subnav} aria-label="Control sections">
      {CONTROL_NAV.map((item) => {
        const active = controlTabActive(path, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`${styles.tab} ${active ? styles.tabActive : ""}`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
