// components/ui/button.tsx — Zinc design token button
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center text-sm font-medium rounded-md transition-colors disabled:pointer-events-none disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1",
  {
    variants: {
      variant: {
        default:     "bg-[var(--accent)] text-white hover:bg-[var(--accent)]/90",
        secondary:   "bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] hover:bg-[var(--panel-hover)]",
        ghost:       "hover:bg-[var(--panel-hover)] text-[var(--text-muted)] hover:text-[var(--text)]",
        destructive: "bg-[var(--error)]/10 text-[var(--error)] border border-[var(--error)]/30 hover:bg-[var(--error)]/20",
        outline:     "border border-[var(--border)] bg-transparent hover:bg-[var(--panel)] text-[var(--text)]",
        link:        "text-[var(--accent)] underline-offset-4 hover:underline bg-transparent p-0 h-auto",
      },
      size: {
        default: "h-9 px-4 py-2 min-h-[44px] sm:min-h-[36px]",
        sm:      "h-7 px-3 text-xs",
        lg:      "h-11 px-6",
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
