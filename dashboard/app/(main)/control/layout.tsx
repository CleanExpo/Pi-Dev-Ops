import ActiveBuildStrip from "@/components/control/ActiveBuildStrip";
import ControlSubnav from "@/components/control/ControlSubnav";
import TopBar from "@/components/control/TopBar";
import styles from "@/components/control/control-deck.module.css";
import type { ReactNode } from "react";

export default function ControlLayout({ children }: { children: ReactNode }) {
  return (
    <div className={`flex flex-col ${styles.shell}`} style={{ height: "100vh", overflow: "hidden" }}>
      <TopBar />
      <div className="px-5 pt-2">
        <ActiveBuildStrip />
      </div>
      <ControlSubnav />
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
}
