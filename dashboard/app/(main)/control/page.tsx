import ControlHubTiles from "@/components/control/ControlHubTiles";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";

export default function ControlPage() {
  return (
    <div className="flex-1 overflow-auto p-4 flex flex-col gap-4 min-h-0">
      <ControlHubTiles />
      <LiveActivityFeed />
    </div>
  );
}
