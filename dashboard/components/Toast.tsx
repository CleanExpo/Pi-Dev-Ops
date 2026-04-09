// components/Toast.tsx — lightweight toast notification system
"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

export type ToastVariant = "success" | "error" | "info";

interface Toast {
  id:      string;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

const COLORS: Record<ToastVariant, { bg: string; border: string; color: string }> = {
  success: { bg: "#0d1a0d", border: "#4ADE80", color: "#4ADE80" },
  error:   { bg: "#1a0808", border: "#F87171", color: "#F87171" },
  info:    { bg: "#0d0d1a", border: "#6B8CFF", color: "#C8C5C0" },
};

const ICONS: Record<ToastVariant, string> = {
  success: "✓",
  error:   "✗",
  info:    "ℹ",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((t) => t.filter((x) => x.id !== id));
    const timer = timers.current.get(id);
    if (timer) { clearTimeout(timer); timers.current.delete(id); }
  }, []);

  const toast = useCallback((message: string, variant: ToastVariant = "info") => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((t) => [...t.slice(-4), { id, message, variant }]); // max 5 at once
    const timer = setTimeout(() => dismiss(id), 4000);
    timers.current.set(id, timer);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}

      {/* Toast container — bottom-right */}
      <div
        aria-live="polite"
        aria-label="Notifications"
        className="fixed bottom-4 right-4 flex flex-col gap-2 z-50"
        style={{ maxWidth: "340px" }}
      >
        {toasts.map((t) => {
          const c = COLORS[t.variant];
          return (
            <div
              key={t.id}
              role="alert"
              className="flex items-start gap-2 px-3 py-2 font-mono text-[11px]"
              style={{
                background:   c.bg,
                border:       `1px solid ${c.border}`,
                color:        c.color,
                animation:    "fadeSlideIn 0.15s ease-out",
              }}
            >
              <span className="shrink-0">{ICONS[t.variant]}</span>
              <span className="flex-1 leading-relaxed" style={{ color: "#F0EDE8" }}>{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                className="shrink-0 font-mono text-[10px] ml-1"
                style={{ color: "#888480" }}
                aria-label="Dismiss"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </ToastContext.Provider>
  );
}
