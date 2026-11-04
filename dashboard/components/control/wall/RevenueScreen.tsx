import styles from "./command-wall.module.css";

/** No revenue or funnel reader exists in this dashboard yet. Never draw sample numbers. */
export default function RevenueScreen() {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyFrame} aria-hidden="true">no data source yet</div>
      <p className={styles.note}>No revenue or funnel source is connected to Mission Control.</p>
      <p className={styles.footnote}>Needs a read-only revenue feed (for example Stripe payouts or CRM won deals) before any number appears here.</p>
    </div>
  );
}
