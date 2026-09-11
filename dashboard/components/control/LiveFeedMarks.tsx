export function PhasePill({ phase }: { phase: string }) {
  const color = {
    spec: "bg-blue-500/20 text-blue-300 border-blue-500/40",
    plan: "bg-purple-500/20 text-purple-300 border-purple-500/40",
    build: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    test: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    ship: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    review: "bg-rose-500/20 text-rose-300 border-rose-500/40",
    evaluating: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    cloning: "bg-slate-500/20 text-slate-300 border-slate-500/40",
    created: "bg-slate-500/20 text-slate-300 border-slate-500/40",
    building: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    running: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  }[phase] || "bg-slate-500/20 text-slate-300 border-slate-500/40";
  return <span className={`px-2 py-0.5 text-xs font-mono rounded border ${color}`}>{phase}</span>;
}

export function LiveDot({ active }: { active: boolean }) {
  return (
    <span className="inline-flex h-2 w-2">
      <span
        className={`absolute inline-flex h-2 w-2 rounded-full ${
          active ? "bg-emerald-400 animate-ping" : "bg-slate-600"
        } opacity-75`}
      />
      <span
        className={`relative inline-flex h-2 w-2 rounded-full ${
          active ? "bg-emerald-500" : "bg-slate-600"
        }`}
      />
    </span>
  );
}
