'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Service, Triage } from '@/lib/content';
import { Button, ButtonLink, Reading } from './primitives';

export interface FinderResultProps {
  top: Service[];
  urgent: boolean;
  brief: string;
  triage: Triage;
  email: string;
  contact: Record<string, string>;
  setContact: (fn: (c: Record<string, string>) => Record<string, string>) => void;
  onRestart: () => void;
}

const CONTACT_FIELDS = [
  { id: 'name', label: 'Name', type: 'text', autoComplete: 'name' },
  { id: 'phone', label: 'Phone', type: 'tel', autoComplete: 'tel' },
  { id: 'email', label: 'Email', type: 'email', autoComplete: 'email' },
  { id: 'property', label: 'Property suburb or address', type: 'text', autoComplete: 'address-level2' },
] as const;

export function FinderResult({
  top, urgent, brief, triage, email, contact, setContact, onRestart,
}: FinderResultProps) {
  const [copied, setCopied] = useState(false);
  const [primary, ...also] = top;
  const mailto = `mailto:${email}?subject=${encodeURIComponent(
    `Assessment request — ${primary.title}`
  )}&body=${encodeURIComponent(brief)}`;

  return (
    <div id="result">
      <div className="overflow-hidden rounded-[16px] border-2 border-primary">
        <div className="bg-primary px-6 py-6 text-primary-foreground sm:px-8">
          <h2 className="text-[length:var(--text-headline)]">Your assessment</h2>
          <p className="mt-1.5 text-[0.95rem] text-white/75">
            Based on what you described. If it does not match what you expected, call and talk it through.
          </p>
        </div>
        <div className="bg-panel px-6 py-7 sm:px-8">
          {urgent && (
            <p className="mb-6 rounded-[8px] border border-l-4 border-accent bg-[color-mix(in_oklab,var(--accent)_12%,var(--panel))] px-5 py-4 text-[0.95rem]">
              <strong className="text-accent-ink">Mention this when you contact us.</strong>{' '}
              {triage.urgency.high}
            </p>
          )}

          <article className="rounded-[12px] border-2 border-accent bg-panel p-6">
            <Reading className="mb-3 inline-block rounded-full bg-accent px-3 py-1 text-[0.68rem] uppercase tracking-[0.12em] text-accent-foreground">
              Recommended
            </Reading>
            <h3 className="text-[1.3rem]">{primary.title}</h3>
            <p className="measure mt-3 text-muted-foreground">{primary.intro}</p>
            <ul className="mt-5 space-y-2">
              {primary.deliverables.slice(0, 3).map((d) => (
                <li key={d} className="flex gap-3 text-[0.94rem] text-muted-foreground">
                  <span className="mt-2 size-1.5 shrink-0 rotate-45 bg-accent" aria-hidden />
                  {d}
                </li>
              ))}
            </ul>
            <Link
              href={`/services/${primary.slug}/`}
              className="mt-5 inline-block font-bold text-primary underline underline-offset-4"
            >
              What this investigation involves →
            </Link>
          </article>

          {also.length > 0 && (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {also.map((s) => (
                <article key={s.slug} className="rounded-[12px] border border-border bg-panel-2 p-5">
                  <Reading className="mb-2 inline-block text-[0.68rem] uppercase tracking-[0.12em] text-muted-foreground">
                    Worth considering
                  </Reading>
                  <h4 className="text-[1.02rem]">{s.title}</h4>
                  <p className="mt-2 text-[0.92rem] text-muted-foreground">{s.short}</p>
                  <Link
                    href={`/services/${s.slug}/`}
                    className="mt-3 inline-block text-[0.92rem] font-bold text-primary underline underline-offset-4"
                  >
                    Read more →
                  </Link>
                </article>
              ))}
            </div>
          )}

          <h3 className="mt-9 text-[1.1rem]">Your details</h3>
          <p className="mt-1.5 text-[0.92rem] text-muted-foreground">
            Optional, but a brief with a location and a contact can be quoted straight away.
            Nothing is sent anywhere until you press the email button.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {CONTACT_FIELDS.map((f) => (
              <div key={f.id}>
                <label htmlFor={`c-${f.id}`} className="mb-1.5 block text-[0.92rem] font-bold">
                  {f.label}
                </label>
                <input
                  id={`c-${f.id}`}
                  type={f.type}
                  autoComplete={f.autoComplete}
                  value={contact[f.id] ?? ''}
                  onChange={(e) => setContact((c) => ({ ...c, [f.id]: e.target.value }))}
                  className="w-full rounded-[4px] border border-border bg-panel px-3.5 py-2.5 text-[1rem]"
                />
              </div>
            ))}
          </div>
          <div className="mt-4">
            <label htmlFor="c-notes" className="mb-1.5 block text-[0.92rem] font-bold">
              Anything else we should know
            </label>
            <textarea
              id="c-notes"
              rows={3}
              value={contact.notes ?? ''}
              onChange={(e) => setContact((c) => ({ ...c, notes: e.target.value }))}
              placeholder="What has already been tried, access constraints, deadlines"
              className="w-full rounded-[4px] border border-border bg-panel px-3.5 py-2.5 text-[1rem]"
            />
          </div>

          <h3 className="mt-9 text-[1.1rem]">Your brief</h3>
          <pre
            id="brief"
            className="reading mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-[8px] border border-border bg-panel-2 p-5 text-[0.86rem] text-muted-foreground"
          >
            {brief}
          </pre>

          <div className="mt-6 flex flex-wrap gap-3">
            <ButtonLink href={mailto} id="emailBtn">Email this to BEWG</ButtonLink>
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(brief);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 4000);
                } catch { /* clipboard blocked; the brief is on screen to copy by hand */ }
              }}
            >
              {copied ? 'Copied' : 'Copy brief'}
            </Button>
            <Button variant="outline" onClick={() => window.print()}>Print or save as PDF</Button>
            <Button
              variant="outline"
              onClick={() => { onRestart(); }}
            >
              Start again
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
