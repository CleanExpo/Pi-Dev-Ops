import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import PortfolioFocus from "@/components/control/PortfolioFocus";
import CommandWall from "@/components/control/wall/CommandWall";

// The wall fills the first screen; project focus, goal intake and the activity
// feed stay reachable directly beneath it (overhaul plan: existing panels preserved).
export default function ControlPage() {
  return (
    <div className="min-h-screen overflow-auto" style={{ background: "#0b0e13" }}>
      <CommandWall />
      <div className="p-4 lg:p-6 flex flex-col gap-5">
        <PortfolioFocus><IdeaPipelinePanel /></PortfolioFocus>
        <LiveActivityFeed />
      </div>
    </div>
  );
}
