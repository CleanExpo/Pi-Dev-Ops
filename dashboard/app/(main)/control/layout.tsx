import ActiveBuildStrip from "@/components/control/ActiveBuildStrip";
import ControlSubnav from "@/components/control/ControlSubnav";
import TopBar from "@/components/control/TopBar";
import type { ReactNode } from "react";

export default function ControlLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col" style={{ height: "100vh", overflow: "hidden" }}>
      <TopBar />
      <div className="px-4 pt-2" style={{ background: "var(--background)" }}>
        <ActiveBuildStrip />
      </div>
      <ControlSubnav />
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
}
