"use client";

import Link from "next/link";
import { CONTROL_SECTIONS } from "@/lib/control/nav";
import styles from "./control-deck.module.css";

export default function ControlHubTiles() {
  return (
    <section aria-label="Control sections">
      <ul className={styles.tiles}>
        {CONTROL_SECTIONS.map((item, index) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className={`${styles.tile} ${index === 0 ? styles.tileFeatured : ""}`}
            >
              <span className={styles.tileLabel}>{index === 0 ? "Primary" : item.label}</span>
              <span className={styles.tileTitle}>{item.title}</span>
              <span className={styles.tileBlurb}>{item.blurb}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
