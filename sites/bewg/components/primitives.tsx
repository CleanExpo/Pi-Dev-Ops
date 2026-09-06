import Link from 'next/link';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

/** A measured value: reading, code, identifier, timestamp. Never prose.
 *  Enforces the brand spec's mono rule in one place. */
export function Reading({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn('reading', className)}>{children}</span>;
}

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-2 rounded-[8px] font-semibold ' +
  'transition-colors duration-150 min-h-11 px-6 py-2.5 text-[0.975rem] no-underline';

const BUTTON_VARIANTS = {
  /* Amber is the finding — at most one of these per screen. */
  primary: 'bg-accent text-accent-foreground hover:brightness-[0.94]',
  secondary: 'bg-primary text-primary-foreground hover:bg-[color-mix(in_oklab,var(--primary)_88%,black)]',
  outline: 'border-2 border-current text-primary hover:bg-primary-soft',
  onDark: 'border-2 border-white/45 text-white hover:bg-white hover:text-primary',
} as const;

export type ButtonVariant = keyof typeof BUTTON_VARIANTS;

export function ButtonLink({
  href, variant = 'primary', className, id, children,
}: {
  href: string; variant?: ButtonVariant; className?: string; id?: string; children: ReactNode;
}) {
  const external = href.startsWith('tel:') || href.startsWith('mailto:');
  const cls = cn(BUTTON_BASE, BUTTON_VARIANTS[variant], className);
  if (external) return <a href={href} id={id} className={cls}>{children}</a>;
  return <Link href={href} id={id} className={cls}>{children}</Link>;
}

export function Button({
  variant = 'primary', className, children, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button className={cn(BUTTON_BASE, BUTTON_VARIANTS[variant], 'cursor-pointer', className)} {...props}>
      {children}
    </button>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn('rounded-[12px] border border-border bg-panel p-6', className)}>{children}</div>
  );
}

/** Standards codes, capability chips. Mono, because they are identifiers. */
export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="reading rounded-[4px] border border-border-subtle bg-panel-2 px-2.5 py-1 text-[0.78rem] text-muted-foreground">
      {children}
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="reading mb-3 text-[0.75rem] uppercase tracking-[0.16em] text-accent-ink">{children}</p>
  );
}

/** Numbered list used for investigation method steps. */
export function Steps({ items }: { items: string[] }) {
  return (
    <ol className="mt-6 space-y-0">
      {items.map((step, i) => (
        <li key={step} className="flex gap-4 border-b border-border-subtle py-4 last:border-0">
          <span
            className="reading mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary text-[0.72rem] text-primary-foreground"
            aria-hidden
          >
            {String(i + 1).padStart(2, '0')}
          </span>
          <span className="text-[0.99rem] text-muted-foreground">{step}</span>
        </li>
      ))}
    </ol>
  );
}

/** Bulleted list with the amber marker. Amber marks findings, never decoration. */
export function Marked({ items }: { items: string[] }) {
  return (
    <ul className="mt-6 space-y-0">
      {items.map((item) => (
        <li key={item} className="flex gap-4 border-b border-border-subtle py-3.5 last:border-0">
          <span className="mt-2.5 size-1.5 shrink-0 rotate-45 bg-accent" aria-hidden />
          <span className="text-[0.99rem] text-muted-foreground">{item}</span>
        </li>
      ))}
    </ul>
  );
}
