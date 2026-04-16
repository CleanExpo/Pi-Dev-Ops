// components/control/ProgressRing.tsx — SVG arc progress ring for SwarmPanel + ModelBadge
"use client";

interface ProgressRingProps {
  value: number;        // 0–100
  size?: number;        // diameter px (default 72)
  strokeWidth?: number;
  colour?: string;
  label?: string;       // centre label — defaults to numeric value
  sublabel?: string;    // small text below the centre label
}

export default function ProgressRing({
  value,
  size = 72,
  strokeWidth = 6,
  colour = "var(--accent)",
  label,
  sublabel,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const r = (size - strokeWidth) / 2;
  const cx = size / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - clamped / 100);
  const fontSize = Math.round(size * 0.22);
  const subFontSize = Math.round(size * 0.14);

  return (
    <svg
      width={size}
      height={size}
      role="img"
      aria-label={`${label ?? clamped} out of 100`}
      style={{ display: "block" }}
    >
      {/* Track ring */}
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth={strokeWidth}
      />
      {/* Fill arc */}
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={colour}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${cx} ${cx})`}
        style={{ transition: "stroke-dashoffset 0.7s cubic-bezier(.4,0,.2,1)" }}
      />
      {/* Centre label */}
      <text
        x={cx}
        y={sublabel ? cx - subFontSize * 0.6 : cx}
        dominantBaseline="middle"
        textAnchor="middle"
        fontSize={fontSize}
        fontFamily="var(--font-mono, monospace)"
        fontWeight="600"
        fill={colour}
      >
        {label ?? clamped}
      </text>
      {sublabel && (
        <text
          x={cx}
          y={cx + fontSize * 0.65}
          dominantBaseline="middle"
          textAnchor="middle"
          fontSize={subFontSize}
          fontFamily="var(--font-sans, system-ui, sans-serif)"
          fill="var(--text-dim)"
        >
          {sublabel}
        </text>
      )}
    </svg>
  );
}
