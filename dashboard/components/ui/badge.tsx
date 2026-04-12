// components/ui/badge.tsx — Bloomberg status badges (monospace, sharp)
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center font-mono text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 border transition-colors",
  {
    variants: {
      variant: {
        default:     "bg-[var(--c-orange)]/10 text-[var(--c-orange)] border-[var(--c-orange)]/40",
        secondary:   "bg-[var(--c-panel)] text-[var(--c-muted)] border-[var(--c-border)]",
        destructive: "bg-red-500/10 text-red-400 border-red-500/30",
        success:     "bg-green-500/10 text-green-400 border-green-500/30",
        warning:     "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
        outline:     "bg-transparent text-[var(--c-chrome)] border-[var(--c-border)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
