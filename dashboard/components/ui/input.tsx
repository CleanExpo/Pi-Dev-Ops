// components/ui/input.tsx — Bloomberg terminal input
import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full bg-[var(--c-panel)] border border-[var(--c-border)]",
          "px-3 py-2 font-mono text-xs text-[var(--c-text)]",
          "placeholder:text-[var(--c-chrome)] placeholder:tracking-widest",
          "focus:outline-none focus:border-[var(--c-orange)] focus:ring-0",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "transition-colors",
          /* iOS zoom prevention */
          "text-base sm:text-xs",
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
