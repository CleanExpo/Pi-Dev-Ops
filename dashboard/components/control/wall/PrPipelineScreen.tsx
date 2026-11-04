import type { PrRow } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";
import { Dot } from "./WallPanel";

/** prRow's reason before the first board read finishes. */
const NOT_READ = "not read yet";

function Count({ value, capped = false }: { value: number | null; capped?: boolean }) {
  if (value === null) return <span className={styles.unknown}>unknown</span>;
  return <span className={styles.big}>{value}{capped ? "+" : ""}</span>;
}

function Row({ row }: { row: PrRow }) {
  return (
    <tr>
      <td>
        <span className={styles.repo}>{row.name}</span>
        {row.reason && (
          <span className={styles.reason}>{row.reason === NOT_READ ? "connecting" : `unavailable: ${row.reason}`}</span>
        )}
      </td>
      {/* Lane counts come from the same capped page as Open, so they carry its marker. */}
      <td><Count value={row.open} capped={row.capped} /></td>
      <td><Count value={row.auditLane} capped={row.capped} /></td>
      <td><Count value={row.needsPhill} capped={row.capped} /></td>
      <td><Count value={row.aging} capped={row.capped} /></td>
      <td><span className={styles.ciCell}><Dot tone={row.ci.tone} />{row.ci.text}</span></td>
    </tr>
  );
}

export default function PrPipelineScreen({ rows }: { rows: PrRow[] }) {
  return (
    <>
      <table className={styles.table}>
        <caption className="sr-only">Open pull requests by repository and stage</caption>
        <thead>
          <tr>
            <th scope="col">Repository</th>
            <th scope="col">Open</th>
            <th scope="col">Audit lane</th>
            <th scope="col">Needs Phill</th>
            <th scope="col">Aging 5d+</th>
            <th scope="col">Main CI</th>
          </tr>
        </thead>
        <tbody>{rows.map((r) => <Row key={r.repo} row={r} />)}</tbody>
      </table>
      <p className={styles.footnote}>
        Counts come from GitHub open pull requests. Audit lane and Needs Phill are sorted from PR labels,
        not from review activity. Release-gate receipts and per-PR check results have no live reader yet,
        so those stages are not shown as numbers.
      </p>
    </>
  );
}
