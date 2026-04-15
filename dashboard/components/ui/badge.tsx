// components/ui/badge.tsx — pill badge with Zinc design tokens
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium border transition-colors",
  {
    variants: {
      variant: {
        default:     "bg-[var(--accent-subtle)] text-[var(--accent)] border-[var(--accent)]/30",
        secondary:   "bg-[var(--panel)] text-[var(--text-muted)] border-[var(--border)]",
        destructive: "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
        success:     "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
        warning:     "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
        outline:     "bg-transparent text-[var(--text-muted)] border-[var(--border)]",
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
