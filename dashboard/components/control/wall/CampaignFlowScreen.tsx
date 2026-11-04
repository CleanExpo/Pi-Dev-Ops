import { CAMPAIGN_HOPS, type PrRow } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";
import { Dot } from "./WallPanel";

function EndNode({ label, row }: { label: string; row: PrRow | undefined }) {
  return (
    <div className={`${styles.node} ${styles.nodeEnd}`}>
      <span className={styles.nodeLabel}>{label}</span>
      <span className={styles.nodeDetail}>
        <Dot tone={row?.ci.tone ?? "idle"} /> code CI {row?.ci.text ?? "unavailable"}
      </span>
      <span className={styles.nodeDetail}>Repository health only, not campaign status.</span>
    </div>
  );
}

export default function CampaignFlowScreen({ crm, synthex }: { crm: PrRow | undefined; synthex: PrRow | undefined }) {
  return (
    <>
      <ol className={styles.flowTrack} aria-label="CRM to Synthex campaign flow">
        <li className={styles.flowItem}><EndNode label="Unite CRM" row={crm} /></li>
        {CAMPAIGN_HOPS.map((hop) => (
          <li key={hop.id} className={styles.flowItem}>
            <span className={styles.hop} aria-hidden="true"><span className={styles.hopLine} data-connected={hop.connected} /></span>
            <div className={styles.node}>
              <span className={styles.nodeLabel}>{hop.label}</span>
              <span className={styles.badge}>{hop.connected ? "connected" : "not connected"}</span>
              <span className={styles.nodeDetail}>{hop.detail}</span>
            </div>
          </li>
        ))}
        <li className={styles.flowItem}>
          <span className={styles.hop} aria-hidden="true"><span className={styles.hopLine} data-connected={false} /></span>
          <EndNode label="Synthex" row={synthex} />
        </li>
      </ol>
      <p className={styles.footnote}>Dashed grey links have no live reader yet. A link animates only once its hop reports real events.</p>
    </>
  );
}
