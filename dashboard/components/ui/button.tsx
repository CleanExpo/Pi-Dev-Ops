// components/ui/button.tsx — Bloomberg-aesthetic shadcn button
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // base — sharp, monospace, uppercase tracking
  "inline-flex items-center justify-center font-mono text-xs font-bold uppercase tracking-widest transition-opacity disabled:pointer-events-none disabled:opacity-30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
  {
    variants: {
      variant: {
        default:     "bg-[var(--c-orange)] text-white hover:opacity-80",
        secondary:   "bg-[var(--c-panel)] text-[var(--c-text)] border border-[var(--c-border)] hover:border-[var(--c-orange)] hover:text-[var(--c-orange)]",
        ghost:       "bg-transparent text-[var(--c-chrome)] hover:text-[var(--c-text)] hover:bg-[var(--c-panel)]",
        destructive: "bg-red-500/10 text-red border border-red-500/30 hover:bg-red-500/20",
        outline:     "border border-[var(--c-orange)] text-[var(--c-orange)] bg-transparent hover:bg-[var(--c-orange)] hover:text-white",
        link:        "text-[var(--c-orange)] underline-offset-4 hover:underline bg-transparent p-0 h-auto",
      },
      size: {
        default: "h-9 px-5 py-2 min-h-[44px] sm:min-h-[36px]",
        sm:      "h-7 px-3 text-[10px] tracking-wider",
        lg:      "h-11 px-8 text-sm",
        icon:    "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
