import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "./utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all duration-200 ease-in-out disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 [&_svg]:transition-transform [&_svg]:duration-200 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-primary/90 hover:shadow-lg hover:shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] [&_svg]:hover:scale-110",
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 hover:shadow-lg hover:shadow-destructive/20 hover:scale-[1.02] active:scale-[0.98] focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60 [&_svg]:hover:scale-110",
        outline:
          "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground hover:shadow-md hover:border-accent-foreground/20 hover:scale-[1.02] active:scale-[0.98] dark:bg-input/30 dark:border-input dark:hover:bg-input/50 [&_svg]:hover:scale-110 [&_svg]:hover:rotate-3",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 hover:shadow-md hover:scale-[1.02] active:scale-[0.98] [&_svg]:hover:scale-110",
        ghost:
          "hover:bg-accent hover:text-accent-foreground hover:shadow-sm hover:scale-[1.02] active:scale-[0.98] dark:hover:bg-accent/50 [&_svg]:hover:scale-110 [&_svg]:hover:rotate-3",
        link: "text-primary underline-offset-4 hover:underline [&_svg]:hover:scale-110 [&_svg]:hover:translate-x-0.5",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        sm: "h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        // RA-1578 — WCAG 2.5.5 AAA 44×44px target. Use on primary CTAs
        // and anywhere the surface is expected to be tapped on mobile
        // (bottom-sheet buttons, sticky CTAs, mobile nav icons).
        touch: "h-11 px-6 py-2 has-[>svg]:px-4",
        "icon-touch": "size-11",
        icon: "size-9",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : "button";

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
