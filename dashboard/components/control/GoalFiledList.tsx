"use client";

import type { FiledTicket } from "@/lib/control/goalErrors";
import styles from "./control-deck.module.css";

export default function GoalFiledList({ tickets }: { tickets: FiledTicket[] }) {
  if (tickets.length === 0) return null;
  return (
    <ul className="mt-4 flex flex-col gap-2">
      {tickets.map((ticket) => (
        <li key={ticket.identifier} className={styles.card}>
          <a href={ticket.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>
            {ticket.identifier}
          </a>
          <span className="block text-[13px] mt-1" style={{ color: "var(--text)" }}>{ticket.title}</span>
          <span className={styles.note}>
            {ticket.state}{ticket.labels.length ? ` · ${ticket.labels.join(", ")}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
