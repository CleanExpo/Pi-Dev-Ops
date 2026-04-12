// components/ui/progress.tsx — Bloomberg-style progress bar
import * as React from "react";
import { cn } from "@/lib/utils";

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number;   // 0-100
  variant?: "default" | "success" | "warning" | "error";
}

const variantColor: Record<string, string> = {
  default: "var(--c-orange)",
  success: "#4ADE80",
  warning: "#FFD166",
  error:   "#F87171",
};

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, variant = "default", ...props }, ref) => (
    <div
      ref={ref}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(
        "relative h-0.5 w-full overflow-hidden bg-[var(--c-border)]",
        className
      )}
      {...props}
    >
      <div
        className="h-full transition-all duration-500 ease-out"
        style={{
          width: `${Math.min(100, Math.max(0, value))}%`,
          background: variantColor[variant] ?? variantColor.default,
        }}
      />
    </div>
  )
);
Progress.displayName = "Progress";

export { Progress };
