// Unite Group — Custom Geometric Mark System
// 24×24 viewBox · 1.5px stroke · sharp corners · no fills (except status indicators)
// Derived from hexagon: angular, precise, architectural

export interface MarkProps {
  size?: number;
  color?: string;
  className?: string;
}

// ─── Navigation Marks ────────────────────────────────────────────────────────

// Pentagon with centered dot — strategic overview
export function CommandCenterMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M12 2 L22 8 L22 16 L12 22 L2 16 L2 8 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <circle cx="12" cy="12" r="2" fill={color}/>
    </svg>
  );
}

// Four quadrant squares with offset — overview grid
export function DashboardMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="2" y="2" width="9" height="9" stroke={color} strokeWidth="1.5"/>
      <rect x="13" y="2" width="9" height="9" stroke={color} strokeWidth="1.5"/>
      <rect x="2" y="13" width="9" height="9" stroke={color} strokeWidth="1.5"/>
      <rect x="13" y="13" width="9" height="5" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

// Three staggered vertical bars — signal/pulse
export function ActivityMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="4" y1="20" x2="4" y2="12" stroke={color} strokeWidth="2.5" strokeLinecap="square"/>
      <line x1="12" y1="20" x2="12" y2="4" stroke={color} strokeWidth="2.5" strokeLinecap="square"/>
      <line x1="20" y1="20" x2="20" y2="8" stroke={color} strokeWidth="2.5" strokeLinecap="square"/>
    </svg>
  );
}

// ECG-style waveform — health pulse
export function HealthMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,14 5,14 8,6 11,20 14,14 17,14 20,10 22,12" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Ascending staircase — growth measurement
export function ReportsMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,22 2,16 8,16 8,10 14,10 14,4 22,4" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
      <line x1="2" y1="22" x2="22" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Two overlapping squares — partnerships
export function ClientsMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="2" y="6" width="14" height="14" stroke={color} strokeWidth="1.5"/>
      <rect x="8" y="2" width="14" height="14" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

// Open book — knowledge
export function WikiMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,4 2,20 12,20 12,4" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
      <polyline points="22,4 22,20 12,20 12,4" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
      <line x1="5" y1="8" x2="9" y2="8" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="5" y1="12" x2="9" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Stacked layers — data pipeline
export function SourcesMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,8 12,4 22,8 12,12 2,8" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <polyline points="2,14 12,18 22,14" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <polyline points="2,11 12,15 22,11" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
    </svg>
  );
}

// Kanban columns — project management
export function ProjectsMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="2" y="2" width="5" height="20" stroke={color} strokeWidth="1.5"/>
      <rect x="9.5" y="2" width="5" height="14" stroke={color} strokeWidth="1.5"/>
      <rect x="17" y="2" width="5" height="9" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

// Three nodes with connecting lines — org chart
export function OrganizationsMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="10" y="2" width="4" height="4" stroke={color} strokeWidth="1.5"/>
      <rect x="2" y="16" width="4" height="6" stroke={color} strokeWidth="1.5"/>
      <rect x="18" y="16" width="4" height="6" stroke={color} strokeWidth="1.5"/>
      <line x1="12" y1="6" x2="12" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="4" y1="16" x2="12" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="20" y1="16" x2="12" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// ─── Priority / Status Marks ─────────────────────────────────────────────────

// Downward-pointing solid triangle — urgency/critical
export function UrgentMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polygon points="12,20 2,4 22,4" fill={color}/>
    </svg>
  );
}

// Double chevron right — high priority
export function HighMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="4,6 12,12 4,18" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
      <polyline points="12,6 20,12 12,18" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Single chevron right — medium priority
export function MedMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="8,6 16,12 8,18" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Precise right-angle checkmark
export function SuccessMark({ size = 14, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,12 9,20 22,4" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Diamond with interior line — alert
export function AlertMark({ size = 14, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polygon points="12,2 22,12 12,22 2,12" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <line x1="12" y1="8" x2="12" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <rect x="11" y="17" width="2" height="2" fill={color}/>
    </svg>
  );
}

// Key shape — owner action required
export function OwnerMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="9" cy="10" r="5" stroke={color} strokeWidth="1.5"/>
      <line x1="13" y1="14" x2="22" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="18" y1="18" x2="22" y2="16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Hexagon with arrow — autonomous system
export function AutoMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4,12 L4,6 L12,2 L20,6 L20,18 L12,22 L4,18" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
      <polyline points="16,8 20,6 22,10" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
    </svg>
  );
}

// ─── Business Identity Marks ─────────────────────────────────────────────────

// Forward slash inside diamond — forward momentum, automation
export function SynthexMark({ size = 20, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polygon points="12,2 22,12 12,22 2,12" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <line x1="8" y1="16" x2="16" y2="8" stroke={color} strokeWidth="2" strokeLinecap="square"/>
    </svg>
  );
}

// Two arcs facing each other — restoration/recovery
export function RestoreAssistMark({ size = 20, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4,12 A8,8 0 0,1 20,12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M20,12 A8,8 0 0,1 4,12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <polyline points="4,8 4,12 8,12" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
    </svg>
  );
}

// Lightning bolt inside bracket — disaster recovery
export function DRPlatformMark({ size = 20, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="4,2 4,22 20,22" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
      <polygon points="14,3 9,13 14,13 10,21" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" fill="none"/>
    </svg>
  );
}

// Three nodes in triangular network — community/practitioners
export function NRPGMark({ size = 20, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="12" cy="5" r="2.5" stroke={color} strokeWidth="1.5"/>
      <circle cx="5" cy="18" r="2.5" stroke={color} strokeWidth="1.5"/>
      <circle cx="19" cy="18" r="2.5" stroke={color} strokeWidth="1.5"/>
      <line x1="12" y1="7.5" x2="6.5" y2="16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="12" y1="7.5" x2="17.5" y2="16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="7.5" y1="18" x2="16.5" y2="18" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Compliance shield with horizontal bars — protection/verification
export function CARSIMark({ size = 20, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M12,2 L20,6 L20,14 C20,18 16,21 12,22 C8,21 4,18 4,14 L4,6 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <line x1="8" y1="10" x2="16" y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="8" y1="14" x2="13" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Linked chain C forms — commerce, supply chain
export function CCWMark({ size = 20, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M14,7 A5,5 0 1,0 14,17" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M10,7 A5,5 0 1,1 10,17" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// ─── System Marks ─────────────────────────────────────────────────────────────

// Right-angle arrow cycle — refresh/sync
export function RefreshMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4,12 A8,8 0 0,1 20,8" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M20,12 A8,8 0 0,1 4,16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <polyline points="16,4 20,8 16,12" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
    </svg>
  );
}

// Square with corner arrow — external link
export function ExternalMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="14,2 22,2 22,10" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
      <line x1="22" y1="2" x2="11" y2="13" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M10,4 L4,4 L4,20 L20,20 L20,14" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
    </svg>
  );
}

// Nodes in sequence — agent pipeline
export function PipelineMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="4" cy="12" r="2.5" stroke={color} strokeWidth="1.5"/>
      <circle cx="12" cy="12" r="2.5" stroke={color} strokeWidth="1.5"/>
      <circle cx="20" cy="12" r="2.5" stroke={color} strokeWidth="1.5"/>
      <line x1="6.5" y1="12" x2="9.5" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="14.5" y1="12" x2="17.5" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Precise rising line — growth/metrics
export function TrendUpMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,20 8,12 14,16 22,4" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
      <polyline points="16,4 22,4 22,10" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Git-branch style — code/deployment
export function BranchMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="6" cy="5" r="2.5" stroke={color} strokeWidth="1.5"/>
      <circle cx="6" cy="19" r="2.5" stroke={color} strokeWidth="1.5"/>
      <circle cx="18" cy="9" r="2.5" stroke={color} strokeWidth="1.5"/>
      <line x1="6" y1="7.5" x2="6" y2="16.5" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M6,7.5 C6,13 18,11.5 18,11.5" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Simple chevron right — directional / active indicator
export function ChevronRightMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="8,4 16,12 8,20" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Search — magnifier outline
export function SearchMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="10" cy="10" r="7" stroke={color} strokeWidth="1.5"/>
      <line x1="15.5" y1="15.5" x2="22" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Clock — time / pending
export function ClockMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.5"/>
      <polyline points="12,7 12,12 16,14" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
    </svg>
  );
}

// Tag — labelling
export function TagMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M2,2 L12,2 L22,12 L12,22 L2,12 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <circle cx="7" cy="7" r="1.5" fill={color}/>
    </svg>
  );
}

// Download arrow — export/PDF
export function DownloadMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="12" y1="3" x2="12" y2="16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <polyline points="6,11 12,17 18,11" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
      <line x1="3" y1="21" x2="21" y2="21" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Expand chevron up/down — collapse toggle
export function ChevronUpMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="4,16 12,8 20,16" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

export function ChevronDownMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="4,8 12,16 20,8" stroke={color} strokeWidth="2" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Plus — add action
export function PlusMark({ size = 14, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="12" y1="3" x2="12" y2="21" stroke={color} strokeWidth="2" strokeLinecap="square"/>
      <line x1="3" y1="12" x2="21" y2="12" stroke={color} strokeWidth="2" strokeLinecap="square"/>
    </svg>
  );
}

// X — close / dismiss
export function CloseMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="4" y1="4" x2="20" y2="20" stroke={color} strokeWidth="2" strokeLinecap="square"/>
      <line x1="20" y1="4" x2="4" y2="20" stroke={color} strokeWidth="2" strokeLinecap="square"/>
    </svg>
  );
}

// Arrow left — back navigation
export function ArrowLeftMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="21" y1="12" x2="3" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <polyline points="10,5 3,12 10,19" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Arrow up-right — open / navigate out
export function ArrowUpRightMark({ size = 12, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="5" y1="19" x2="19" y2="5" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <polyline points="9,5 19,5 19,15" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Building — org / company
export function BuildingMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="2" y="4" width="13" height="18" stroke={color} strokeWidth="1.5"/>
      <rect x="15" y="10" width="7" height="12" stroke={color} strokeWidth="1.5"/>
      <line x1="6" y1="8" x2="6" y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="10" y1="8" x2="10" y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="6" y1="14" x2="6" y2="16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="10" y1="14" x2="10" y2="16" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Users / team
export function UsersMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="9" cy="8" r="4" stroke={color} strokeWidth="1.5"/>
      <path d="M2,21 C2,17 5,14 9,14 C13,14 16,17 16,21" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M16,6 C17,6.5 18,7.8 18,9.5 C18,11.2 17,12.5 16,13" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M18,14 C20,15 22,17 22,21" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// File / document
export function FileMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4,2 L14,2 L20,8 L20,22 L4,22 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <polyline points="14,2 14,8 20,8" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <line x1="8" y1="13" x2="16" y2="13" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="8" y1="17" x2="13" y2="17" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Settings / gear (minimal: hexagon ring)
export function SettingsMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="12" cy="12" r="3" stroke={color} strokeWidth="1.5"/>
      <path d="M12,2 L14,5 L17,4 L19,7 L22,8 L21,11 L22,14 L19,15 L17,18 L14,17 L12,20 L10,17 L7,18 L5,15 L2,14 L3,11 L2,8 L5,7 L7,4 L10,5 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
    </svg>
  );
}

// Log out — exit session
export function LogOutMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M9,4 L4,4 L4,20 L9,20" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
      <line x1="21" y1="12" x2="10" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <polyline points="15,7 21,12 15,17" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Home — dashboard root
export function HomeMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <polyline points="2,12 12,3 22,12" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
      <path d="M5,10 L5,21 L10,21 L10,16 L14,16 L14,21 L19,21 L19,10" stroke={color} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
    </svg>
  );
}

// Folder — projects / tasks
export function FolderMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M2,6 L2,20 L22,20 L22,8 L10,8 L8,6 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
    </svg>
  );
}

// Check square — task complete
export function CheckSquareMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3" y="3" width="18" height="18" stroke={color} strokeWidth="1.5"/>
      <polyline points="7,12 10,16 17,8" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Dollar sign — financials
export function DollarMark({ size = 14, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="12" y1="2" x2="12" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M17,7 C17,7 15,5 12,5 C9,5 7,7 7,9 C7,11 9,12 12,12 C15,12 17,13 17,15 C17,17 15,19 12,19 C9,19 7,17 7,17" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Calendar — dates / timeline
export function CalendarMark({ size = 14, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="2" y="4" width="20" height="18" stroke={color} strokeWidth="1.5"/>
      <line x1="2" y1="10" x2="22" y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="8" y1="2" x2="8" y2="7" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="16" y1="2" x2="16" y2="7" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Rss / feed — sources
export function FeedMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="5" cy="19" r="2" fill={color}/>
      <path d="M4,13 C8,13 11,16 11,20" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M4,7 C11,7 17,13 17,20" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <path d="M4,2 C14,2 22,10 22,20" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Check circle — done / all clear
export function CheckCircleMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.5"/>
      <polyline points="7,12 10,16 17,8" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="square"/>
    </svg>
  );
}

// Loader — spinning progress indicator (replace Loader2)
export function LoaderMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="12" y1="2" x2="12" y2="6" stroke={color} strokeWidth="2" strokeLinecap="square"/>
      <line x1="12" y1="18" x2="12" y2="22" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.3"/>
      <line x1="4.22" y1="4.22" x2="7.05" y2="7.05" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.7"/>
      <line x1="16.95" y1="16.95" x2="19.78" y2="19.78" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.2"/>
      <line x1="2" y1="12" x2="6" y2="12" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.5"/>
      <line x1="18" y1="12" x2="22" y2="12" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.15"/>
      <line x1="4.22" y1="19.78" x2="7.05" y2="16.95" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.4"/>
      <line x1="16.95" y1="7.05" x2="19.78" y2="4.22" stroke={color} strokeWidth="2" strokeLinecap="square" opacity="0.1"/>
    </svg>
  );
}

// Eye — password reveal
export function EyeMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M2,12 C2,12 5,6 12,6 C19,6 22,12 22,12 C22,12 19,18 12,18 C5,18 2,12 2,12 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <circle cx="12" cy="12" r="3" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

// Eye off — hide password
export function EyeOffMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M2,12 C2,12 5,6 12,6 C19,6 22,12 22,12 C22,12 19,18 12,18 C5,18 2,12 2,12 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
      <circle cx="12" cy="12" r="3" stroke={color} strokeWidth="1.5"/>
      <line x1="3" y1="3" x2="21" y2="21" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Mail — email input
export function MailMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="2" y="4" width="20" height="16" stroke={color} strokeWidth="1.5"/>
      <polyline points="2,4 12,14 22,4" stroke={color} strokeWidth="1.5" strokeLinejoin="miter"/>
    </svg>
  );
}

// Key — password / auth
export function KeyMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="8" cy="12" r="5" stroke={color} strokeWidth="1.5"/>
      <line x1="13" y1="12" x2="22" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="18" y1="10" x2="18" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <line x1="20" y1="12" x2="20" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
    </svg>
  );
}

// Bar chart — analytics / reports (simple 3-bar)
export function BarChartMark({ size = 16, color = 'currentColor', className }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <line x1="3" y1="22" x2="21" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="square"/>
      <rect x="4" y="14" width="4" height="8" stroke={color} strokeWidth="1.5"/>
      <rect x="10" y="8" width="4" height="14" stroke={color} strokeWidth="1.5"/>
      <rect x="16" y="4" width="4" height="18" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}
