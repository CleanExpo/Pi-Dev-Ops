import type { PrRow } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";
import { Dot } from "./WallPanel";

function Count({ value, capped = false }: { value: number | null; capped?: boolean }) {
  if (value === null) return <span className={styles.unknown}>unknown</span>;
  return <span className={styles.big}>{value}{capped ? "+" : ""}</span>;
}

function Row({ row }: { row: PrRow }) {
  return (
    <tr>
      <td>
        <span className={styles.repo}>{row.name}</span>
        {row.reason && <span className={styles.reason}>unavailable: {row.reason}</span>}
      </td>
      <td><Count value={row.open} capped={row.capped} /></td>
      <td><Count value={row.review} /></td>
      <td><Count value={row.needsPhill} /></td>
      <td><Count value={row.aging} /></td>
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
            <th scope="col">In review</th>
            <th scope="col">Needs Phill</th>
            <th scope="col">Aging 5d+</th>
            <th scope="col">Main CI</th>
          </tr>
        </thead>
        <tbody>{rows.map((r) => <Row key={r.repo} row={r} />)}</tbody>
      </table>
      <p className={styles.footnote}>
        Counts come from GitHub open pull requests. Release-gate receipts and per-PR check results have
        no live reader yet, so those stages are not shown as numbers.
      </p>
    </>
  );
}
