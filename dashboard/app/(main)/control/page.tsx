import FleetTile from "@/components/control/FleetTile";
import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import FlowBoard from "@/components/control/FlowBoard";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import PortfolioFocus from "@/components/control/PortfolioFocus";

export default function ControlPage() {
  return (
    <div className="min-h-screen overflow-auto" style={{ background: "#061723" }}>
      <div className="p-4 lg:p-6 flex flex-col gap-5">
        <section aria-labelledby="nexus-north-star" className="rounded-2xl border border-teal-400/40 bg-[#0d2e36] px-5 py-5 text-[#edf9f5] lg:px-7">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-200">Unite-Group Nexus · North Star</p>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 id="nexus-north-star" className="text-2xl font-semibold tracking-tight lg:text-3xl">Built for the Hard Day</h1>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[#c5dedb]">We earn trust when conditions are hardest: tell the truth early, care for the people doing the work, make clear decisions, and verify the recovery.</p>
            </div>
            <a className="rounded-lg border border-teal-200/60 px-4 py-2 text-sm font-semibold text-teal-100 hover:bg-teal-300/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-200" href="https://github.com/CleanExpo/Pi-Dev-Ops/blob/main/docs/governance/NEXUS-NORTH-STAR.md" target="_blank" rel="noopener noreferrer">Read the North Star</a>
          </div>
        </section>
        <PortfolioFocus><IdeaPipelinePanel /></PortfolioFocus>
        <FleetTile />
        <LiveActivityFeed />
      </div>
    </div>
  );
}
