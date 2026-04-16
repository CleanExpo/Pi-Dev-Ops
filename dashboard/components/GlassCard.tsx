import { ReactNode } from "react"

interface GlassCardProps {
  title?: string
  titleRight?: ReactNode
  accentColor?: string
  noPadding?: boolean
  className?: string
  children: ReactNode
}

export function GlassCard({
  title,
  titleRight,
  accentColor = "var(--accent, #f59e0b)",
  noPadding = false,
  className = "",
  children,
}: GlassCardProps) {
  return (
    <div
      className={`relative rounded-lg border overflow-hidden ${className}`}
      style={{
        background: "var(--card, hsl(240 10% 6%))",
        borderColor: "var(--border, rgba(255,255,255,0.10))",
        boxShadow: "0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
      }}
    >
      {/* Accent fade top-left */}
      <div
        className="absolute top-0 left-0 right-0 h-[1px] pointer-events-none"
        style={{
          background: `linear-gradient(90deg, ${accentColor}40, transparent 60%)`,
        }}
      />

      {(title || titleRight) && (
        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border, rgba(255,255,255,0.08))" }}>
          {title && (
            <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-muted, rgba(255,255,255,0.45))", letterSpacing: "0.06em" }}>
              {title}
            </span>
          )}
          {titleRight && <div className="flex items-center gap-2">{titleRight}</div>}
        </div>
      )}

      <div className={noPadding ? "" : "p-4"}>{children}</div>
    </div>
  )
}
