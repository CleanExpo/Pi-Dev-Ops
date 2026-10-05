import type { MissionControlLive } from "@/lib/control/mission-control-live";
import { founderReadout } from "@/lib/control/founder-readout";

export default function FounderNorthStarReadout({ live }: { live: MissionControlLive | null }) {
  const answers = founderReadout(live);
  return (
    <section aria-labelledby="founder-readout-title" className="relative mt-6 rounded-2xl border border-teal-400/40 bg-[#0a2633] p-4 lg:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="founder-readout-title" className="text-lg font-semibold text-teal-100">The founder’s five answers</h3>
        <p className="text-xs text-slate-300">Source timestamp {live?.ts && !Number.isNaN(Date.parse(live.ts)) ? new Date(live.ts).toLocaleString("en-AU") : "unknown"} · refreshes every 30 seconds</p>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {answers.map((row) => (
          <article key={row.question} className="rounded-xl border border-[#406d78] bg-[#0d303d] p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-teal-200">{row.question}</h4>
            <p className="mt-3 text-sm font-semibold text-white">{row.answer}</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">{row.detail}</p>
            <a className="mt-3 inline-block text-xs text-teal-200 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-teal-200" href={row.href}>Source: {row.source}</a>
          </article>
        ))}
      </div>
    </section>
  );
}
