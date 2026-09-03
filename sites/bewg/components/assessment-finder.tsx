'use client';

import { useMemo, useState } from 'react';
import type { Service, Triage } from '@/lib/content';
import { Button, Reading } from './primitives';
import { FinderResult } from './finder-result';
import { cn } from '@/lib/cn';

/** Answers that mean "tell us when you call" — active water or a vulnerable occupant. */
const URGENT_ANSWERS = new Set([
  'Flood, burst pipe or storm damage',
  'Water stain or active leak',
  'Ongoing symptoms, medical advice already sought',
  'Someone with asthma, allergy or immune vulnerability lives here',
]);

const CONTACT_FIELDS = [
  { id: 'name', label: 'Name', type: 'text', autoComplete: 'name' },
  { id: 'phone', label: 'Phone', type: 'tel', autoComplete: 'tel' },
  { id: 'email', label: 'Email', type: 'email', autoComplete: 'email' },
  { id: 'property', label: 'Property suburb or address', type: 'text', autoComplete: 'address-level2' },
] as const;

type Answers = Record<string, string[]>;
type Contact = Record<string, string>;

function rank(answers: Answers, triage: Triage): { slug: string; n: number }[] {
  const totals: Record<string, number> = {};
  for (const q of triage.questions) {
    for (const picked of answers[q.id] ?? []) {
      const opt = q.options.find((o) => o.value === picked);
      if (!opt) continue;
      for (const [slug, w] of Object.entries(opt.weights)) totals[slug] = (totals[slug] ?? 0) + w;
    }
  }
  const ordered = Object.entries(totals)
    .map(([slug, n]) => ({ slug, n }))
    .sort((a, b) => b.n - a.n);
  /* An answer set carrying no weights still deserves a route. */
  return ordered.length ? ordered : [{ slug: 'mould-iaq-investigation', n: 0 }];
}

function buildBrief(
  answers: Answers, triage: Triage, top: Service[], contact: Contact, urgent: boolean
): string {
  const L: string[] = ['BEWG ASSESSMENT BRIEF', `Generated ${new Date().toLocaleString('en-AU')}`, ''];
  L.push('RECOMMENDED ASSESSMENT');
  top.forEach((s, i) => L.push(`  ${i === 0 ? 'Primary:  ' : 'Secondary:'} ${s.title}`));
  if (urgent) L.push('', 'PRIORITY: active water or a vulnerable occupant reported.');
  L.push('', 'CONTACT');
  for (const f of CONTACT_FIELDS) L.push(`  ${f.label.padEnd(28)}${contact[f.id]?.trim() || '—'}`);
  L.push('', 'REPORTED SITUATION');
  for (const q of triage.questions) {
    L.push(`  ${q.label}`);
    const picked = answers[q.id] ?? [];
    (picked.length ? picked : ['—']).forEach((p) => L.push(`    - ${p}`));
  }
  if (contact.notes?.trim()) {
    L.push('', 'ADDITIONAL NOTES', `  ${contact.notes.trim().replace(/\n/g, '\n  ')}`);
  }
  return L.join('\n');
}

export function AssessmentFinder({
  triage, services, email,
}: { triage: Triage; services: Service[]; email: string }) {
  const [answers, setAnswers] = useState<Answers>({});
  const [contact, setContact] = useState<Contact>({});
  const [submitted, setSubmitted] = useState(false);
  const [showError, setShowError] = useState(false);

  const answered = triage.questions.filter((q) => (answers[q.id] ?? []).length > 0).length;
  const complete = answered === triage.questions.length;

  const result = useMemo(() => {
    if (!submitted) return null;
    const ranked = rank(answers, triage).slice(0, 3);
    const top = ranked
      .map((r) => services.find((s) => s.slug === r.slug))
      .filter((s): s is Service => Boolean(s));
    const urgent = Object.values(answers).flat().some((a) => URGENT_ANSWERS.has(a));
    return { top, urgent, brief: buildBrief(answers, triage, top, contact, urgent) };
  }, [submitted, answers, contact, triage, services]);

  function toggle(q: { id: string; multi: boolean }, value: string) {
    setShowError(false);
    setAnswers((prev) => {
      const cur = prev[q.id] ?? [];
      if (!q.multi) return { ...prev, [q.id]: [value] };
      return { ...prev, [q.id]: cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value] };
    });
  }

  if (result) {
    return (
      <FinderResult
        top={result.top}
        urgent={result.urgent}
        brief={result.brief}
        triage={triage}
        email={email}
        contact={contact}
        setContact={setContact}
        onRestart={() => { setSubmitted(false); setAnswers({}); setShowError(false); }}
      />
    );
  }

  return (
    <form
      id="triage"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (!complete) { setShowError(true); return; }
        setSubmitted(true);
      }}
    >
      <div className="mb-8 h-1.5 overflow-hidden rounded-full bg-border-subtle" aria-hidden>
        <div
          className="h-full bg-accent transition-[width] duration-300"
          style={{ width: `${(answered / triage.questions.length) * 100}%` }}
        />
      </div>

      {triage.questions.map((q, i) => (
        <fieldset
          key={q.id}
          data-index={i}
          className="mb-5 rounded-[12px] border border-border bg-panel p-6"
        >
          <legend className="px-1 text-[1.06rem] font-extrabold">
            <Reading className="mr-2 text-muted-foreground">{String(i + 1).padStart(2, '0')}</Reading>
            {q.label}
          </legend>
          {q.help && <p className="mt-2 text-[0.9rem] text-muted-foreground">{q.help}</p>}
          <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
            {q.options.map((o) => {
              const on = (answers[q.id] ?? []).includes(o.value);
              return (
                <label
                  key={o.value}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-[8px] border px-4 py-3 text-[0.96rem] transition-colors',
                    on
                      ? 'border-primary bg-primary-soft shadow-[inset_0_0_0_1px_var(--primary)]'
                      : 'border-border bg-panel hover:border-primary hover:bg-panel-2'
                  )}
                >
                  <input
                    type={q.multi ? 'checkbox' : 'radio'}
                    name={q.id}
                    value={o.value}
                    checked={on}
                    onChange={() => toggle(q, o.value)}
                    className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
                  />
                  <span>{o.value}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}

      {showError && (
        <p id="formErr" className="mb-4 font-bold text-destructive">
          Answer every question above to see your result.
        </p>
      )}
      <Button type="submit">See my result</Button>
    </form>
  );
}
