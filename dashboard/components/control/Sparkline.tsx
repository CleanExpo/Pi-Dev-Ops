// components/control/Sparkline.tsx — mini sparkline for HealthGrid tiles
// Renders a 48×14 px SVG polyline. When data.length < 2, shows a flat dashed line.
"use client";

interface SparklineProps {
  data: number[];    // 0–100 values (oldest first)
  width?: number;
  height?: number;
  colour?: string;
}

export default function Sparkline({
  data,
  width = 48,
  height = 14,
  colour = "var(--accent)",
}: SparklineProps) {
  if (data.length < 2) {
    // Flat dashed placeholder
    return (
      <svg width={width} height={height} aria-hidden="true">
        <line
          x1={2}
          y1={height / 2}
          x2={width - 2}
          y2={height / 2}
          stroke="var(--border)"
          strokeWidth={1}
          strokeDasharray="3 2"
        />
      </svg>
    );
  }

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pad = 1.5;

  const points = data
    .map((v, i) => {
      const x = pad + (i / (data.length - 1)) * (width - pad * 2);
      const y = pad + ((max - v) / range) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Filled area under the line
  const firstX = pad;
  const lastX = (pad + (width - pad * 2)).toFixed(1);
  const bottom = (height - pad).toFixed(1);
  const areaPoints = `${firstX},${bottom} ${points} ${lastX},${bottom}`;

  return (
    <svg width={width} height={height} aria-hidden="true">
      {/* Fill */}
      <polygon
        points={areaPoints}
        fill={colour}
        fillOpacity={0.12}
      />
      {/* Line */}
      <polyline
        points={points}
        fill="none"
        stroke={colour}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Last point dot */}
      {data.length > 0 && (() => {
        const last = data[data.length - 1];
        const lx = (pad + (width - pad * 2)).toFixed(1);
        const ly = (pad + ((max - last) / range) * (height - pad * 2)).toFixed(1);
        return <circle cx={lx} cy={ly} r={2} fill={colour} />;
      })()}
    </svg>
  );
}
