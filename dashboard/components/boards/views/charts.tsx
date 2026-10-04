"use client";
// RA-7898 — small chart pieces shared by the second views. One data accent for
// magnitude; status colours only beside a text label; text in ink tokens.

import type { Tone } from "@/lib/boards/views/shapes";
import styles from "./views.module.css";

export function Dot({ tone, label }: { tone: Tone | "accent"; label?: string }) {
  return <span className={styles.dot} data-tone={tone === "accent" ? undefined : tone} title={label} aria-hidden={label ? undefined : true} />;
}

export function Unexpected({ what }: { what: string }) {
  return <p className={styles.empty}>The {what} source answered with a shape this view does not recognise. Nothing is shown rather than a guess.</p>;
}

export function Nothing({ text }: { text: string }) {
  return <p className={styles.empty}>{text}</p>;
}

export interface Bar { label: string; value: number; tone?: "bad" }

/** Horizontal bars against a shared maximum. Each bar's value is printed beside it. */
export function Bars({ bars, max, suffix = "" }: { bars: readonly Bar[]; max?: number; suffix?: string }) {
  const top = max ?? Math.max(1, ...bars.map((b) => b.value));
  return (
    <div className={styles.bars}>
      {bars.map((b) => (
        <div key={b.label} className={styles.bar} title={`${b.label}: ${b.value}${suffix}`}>
          <span className={styles.truncate}>{b.label}</span>
          <div className={styles.track}><div className={styles.fill} data-tone={b.tone} style={{ width: `${Math.min(100, (b.value / top) * 100)}%` }} /></div>
          <span className={styles.value}>{b.value}{suffix}</span>
        </div>
      ))}
    </div>
  );
}

export interface Slice { label: string; value: number; color: string }

/** A donut with a centre figure and a labelled legend (identity is never colour alone). */
export function Ring({ slices, center, sub }: { slices: readonly Slice[]; center: string; sub?: string }) {
  const size = 112, stroke = 12, r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const total = slices.reduce((s, x) => s + x.value, 0);
  let offset = 0;
  return (
    <div className={styles.ringWrap}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${center} ${sub ?? ""}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--board-sunk)" strokeWidth={stroke} />
        {total > 0 && slices.filter((s) => s.value > 0).map((s) => {
          const len = (s.value / total) * c;
          const el = (
            <circle key={s.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={s.color} strokeWidth={stroke}
              strokeDasharray={`${Math.max(len - 2, 0.01)} ${c}`} strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}><title>{`${s.label}: ${s.value}`}</title></circle>
          );
          offset += len;
          return el;
        })}
        <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" fill="var(--board-ink)" fontSize="20" fontWeight="600">{center}</text>
        {sub && <text x="50%" y="65%" textAnchor="middle" dominantBaseline="middle" fill="var(--board-ink-3)" fontSize="10.5">{sub}</text>}
      </svg>
      <div className={styles.legend}>
        {slices.map((s) => (
          <div key={s.label}><span className={styles.dot} style={{ background: s.color }} aria-hidden />{s.label}<b>{s.value}</b></div>
        ))}
      </div>
    </div>
  );
}
