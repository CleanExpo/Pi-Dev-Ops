// components/ui/input.tsx — Zinc design token input
import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md bg-[var(--panel)] border border-[var(--border)]",
          "px-3 py-2 text-sm text-[var(--text)]",
          "placeholder:text-[var(--text-dim)]",
          "focus:outline-none focus:border-[var(--accent)] focus:ring-0",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "transition-colors",
          /* iOS zoom prevention */
          "text-base sm:text-sm",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
