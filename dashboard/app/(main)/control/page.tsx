import Link from "next/link";
import ControlHubTiles from "@/components/control/ControlHubTiles";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import styles from "@/components/control/control-deck.module.css";

export default function ControlPage() {
  return (
    <div className="flex-1 overflow-auto min-h-0">
      <header className={styles.hero}>
        <div>
          <div className={styles.kicker}>Pi CEO · Control</div>
          <h1 className={styles.title}>Command deck</h1>
          <p className={styles.lede}>
            State a goal. Review the tickets. Approve before Linear is written.
            Everything else on this deck is a dedicated surface — not a scroll dump.
          </p>
        </div>
        <Link href="/control/goal" className={styles.cta}>
          File a goal →
        </Link>
      </header>
      <div className="px-5 pb-8 flex flex-col gap-5">
        <ControlHubTiles />
        <LiveActivityFeed />
      </div>
    </div>
  );
}
