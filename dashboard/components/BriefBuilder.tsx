// components/BriefBuilder.tsx — scan-powered brief textarea with template suggestions
"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface BriefBuilderProps {
  repoUrl: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

interface ScanResult {
  language?: string;
  framework?: string;
  summary?: string;
  tech_stack?: string[];
  // server may return camelCase too
  techStack?: string[];
}

type TemplateKey = "bug" | "feature" | "refactor" | "tests";

function buildTemplates(scan: ScanResult | null): Record<TemplateKey, string> {
  const stack = scan?.tech_stack ?? scan?.techStack ?? [];
  const lang = scan?.language ?? (stack[0] ?? "the codebase");
  const framework = scan?.framework ?? (stack[1] ?? "");
  const context = framework ? `${lang}/${framework}` : lang;

  return {
    bug: `Scope: Bug fix\nFocus areas: Reproduce the failure, identify root cause, apply minimal targeted fix\nContext: ${context} — investigate the defect, add a regression test, verify no side-effects`,
    feature: `Scope: New feature\nFocus areas: Design the interface, implement end-to-end, cover with tests\nContext: ${context} — deliver a clean, well-tested addition that follows existing conventions`,
    refactor: `Scope: Refactor\nFocus areas: Improve structure, eliminate duplication, reduce complexity without changing behaviour\nContext: ${context} — leave every file touched in better shape than before; no regressions`,
    tests: `Scope: Test & fix failures\nFocus areas: Run the full test suite, diagnose each failure, fix root causes\nContext: ${context} — all tests must pass; add missing coverage where gaps are found`,
  };
}

const TEMPLATE_BUTTONS: { key: TemplateKey; label: string }[] = [
  { key: "bug",      label: "Fix a bug" },
  { key: "feature",  label: "Add a feature" },
  { key: "refactor", label: "Refactor" },
  { key: "tests",    label: "Run tests & fix failures" },
];

const MIN_ROWS = 4;
const MAX_ROWS = 12;
const LINE_HEIGHT_PX = 20; // matches text-sm leading

export default function BriefBuilder({ repoUrl, value, onChange, disabled }: BriefBuilderProps) {
  const [scan, setScan]           = useState<ScanResult | null>(null);
  const [scanning, setScanning]   = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef    = useRef<AbortController | null>(null);

  // Auto-grow textarea up to MAX_ROWS
  const autoGrow = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = MAX_ROWS * LINE_HEIGHT_PX + 16; // +padding
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, []);

  useEffect(() => {
    autoGrow();
  }, [value, autoGrow]);

  // Fetch scan whenever repoUrl changes to a non-empty value
  useEffect(() => {
    if (!repoUrl.trim()) {
      setScan(null);
      setShowTemplates(false);
      return;
    }

    // Cancel any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const timer = setTimeout(() => controller.abort(), 5000);

    setScanning(true);
    setScan(null);
    setShowTemplates(false);

    fetch(`/api/scan?repo_url=${encodeURIComponent(repoUrl.trim())}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) return;
        const data = await res.json() as ScanResult;
        setScan(data);
        setShowTemplates(true);
      })
      .catch(() => {
        // Silent failure — template buttons just stay hidden
      })
      .finally(() => {
        clearTimeout(timer);
        setScanning(false);
      });

    return () => {
      abortRef.current?.abort();
      clearTimeout(timer);
    };
  }, [repoUrl]);

  function applyTemplate(key: TemplateKey) {
    const templates = buildTemplates(scan);
    onChange(templates[key]);
    textareaRef.current?.focus();
  }

  const minHeight = `${MIN_ROWS * LINE_HEIGHT_PX + 16}px`;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {/* Template buttons — only shown after successful scan */}
      {showTemplates && (
        <div className="flex flex-wrap gap-1.5">
          {TEMPLATE_BUTTONS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => applyTemplate(key)}
              disabled={disabled}
              className="px-2.5 py-1 rounded text-[11px] font-medium transition-colors disabled:opacity-40"
              style={{
                background: "var(--accent-subtle)",
                color: "var(--accent)",
                border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "color-mix(in srgb, var(--accent) 15%, transparent)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "var(--accent-subtle)";
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Brief textarea */}
      <div className="relative">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => { onChange(e.target.value); autoGrow(); }}
          placeholder="Brief (optional) — describe what you want the agent to do"
          disabled={disabled}
          rows={MIN_ROWS}
          className="w-full rounded-md px-3 py-2 text-sm resize-none disabled:opacity-50 transition-colors outline-none"
          style={{
            background: "var(--panel)",
            color: "var(--text)",
            border: "1px solid var(--border)",
            minHeight,
            lineHeight: `${LINE_HEIGHT_PX}px`,
            // iOS zoom prevention
            fontSize: "16px",
          }}
          aria-label="Analysis brief"
          onFocus={(e) => { (e.target as HTMLTextAreaElement).style.borderColor = "var(--accent)"; }}
          onBlur={(e)  => { (e.target as HTMLTextAreaElement).style.borderColor = "var(--border)"; }}
        />

        {/* Scanning indicator — subtle, bottom-right of textarea */}
        {scanning && (
          <span
            className="absolute bottom-2 right-2.5 text-[10px] font-mono pointer-events-none"
            style={{ color: "var(--text-dim)" }}
            aria-live="polite"
          >
            Analysing repo…
          </span>
        )}
      </div>
    </div>
  );
}
