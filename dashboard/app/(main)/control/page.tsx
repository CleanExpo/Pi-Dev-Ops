import FleetTile from "@/components/control/FleetTile";
import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import PortfolioFocus from "@/components/control/PortfolioFocus";

export default function ControlPage() {
  return (
    <div className="min-h-screen overflow-auto" style={{ background: "#061723" }}>
      <div className="p-4 lg:p-6 flex flex-col gap-5">
        <PortfolioFocus><IdeaPipelinePanel /></PortfolioFocus>
        <FleetTile />
        <LiveActivityFeed />
      </div>
    </div>
  );
}
