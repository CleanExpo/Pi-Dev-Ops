"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CONTROL_NAV, isSpecialistControlSlug } from "@/lib/control/nav";
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
            title={item.blurb}
            className={`${styles.tab} ${active ? styles.tabActive : ""} ${isSpecialistControlSlug(item.slug) ? styles.tabMuted : ""}`}
          >
            {item.label}
          </Link>
        );
      })}
      {/* RA-7898: boards have their own link and are not a CONTROL_SECTIONS entry. */}
      <Link
        href="/control/boards"
        aria-current={path.startsWith("/control/boards") ? "page" : undefined}
        title="Your own boards of modules"
        className={`${styles.tab} ${path.startsWith("/control/boards") ? styles.tabActive : ""}`}
      >
        Boards
      </Link>
    </nav>
  );
}
