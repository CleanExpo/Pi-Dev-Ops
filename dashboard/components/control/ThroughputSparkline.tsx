// ThroughputSparkline — Mission Control's 24h session-throughput chart.
//
// Distinct from ./Sparkline, which is the 48x14 HealthGrid tile trend. This one
// is the large 200x40 hero chart with its own total, and it was previously
// inlined in LiveActivityFeed.tsx (held at its baseline by the size gate).
"use client";

const W = 200;
const H = 40;

export default function ThroughputSparkline({ data }: { data: number[] }) {
  // A missing or empty series is a real state (partial payload, backend down),
  // not an error. This used to be `Math.max(...data, 1)` on an undefined value,
  // so the whole cockpit threw whenever the backend was actually up.
  if (!Array.isArray(data) || data.length === 0) {
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold text-slate-600 tabular-nums">—</span>
          <span className="text-xs text-text-muted">sessions / 24h</span>
        </div>
        <div style={{ width: W, height: H }} className="flex items-center">
          <span className="text-xs text-text-muted">no throughput data</span>
        </div>
      </div>
    );
  }

  const max = Math.max(...data, 1);
  const step = W / (data.length - 1 || 1);
  const x = (i: number) => (i * step).toFixed(1);
  const y = (v: number) => (H - (v / max) * H).toFixed(1);
  const points = data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const total = data.reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-cyan-400 tabular-nums">{total}</span>
        <span className="text-xs text-text-muted">sessions / 24h</span>
      </div>
      <svg width={W} height={H} className="overflow-visible">
        <polygon points={`0,${H} ${points} ${W},${H}`} fill="rgb(6 182 212 / 0.15)" />
        <polyline
          points={points}
          fill="none"
          stroke="rgb(6 182 212)"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        {data.map((v, i) =>
          v > 0 ? <circle key={i} cx={x(i)} cy={y(v)} r="2" fill="rgb(6 182 212)" /> : null,
        )}
      </svg>
    </div>
  );
}
