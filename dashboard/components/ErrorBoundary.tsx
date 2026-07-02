// components/ErrorBoundary.tsx — React error boundary with Bloomberg aesthetic
"use client";

import { Component, type ReactNode } from "react";
import { CSS } from "@/lib/brand-tokens";

interface Props {
  children:  ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("[ErrorBoundary]", error.message, info.componentStack);
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          className="dark flex flex-col items-center justify-center h-full px-8 py-12 font-mono"
          style={{ background: "var(--background)", color: "var(--text)" }}
        >
          <div
            className="w-full max-w-md p-6"
            style={{ border: `1px solid ${CSS.error}`, background: "var(--panel)" }}
          >
            <div className="flex items-center gap-2 mb-4">
              <span className="text-[14px]" style={{ color: CSS.error }}>✗</span>
              <span className="text-[11px] uppercase tracking-widest" style={{ color: CSS.error }}>
                Component Error
              </span>
            </div>
            <p className="text-[11px] mb-4 leading-relaxed" style={{ color: "var(--text-muted)" }}>
              {this.state.error.message}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="font-mono text-[10px] px-4 py-1.5 tracking-wider"
              style={{ background: CSS.accent, color: CSS.onAccent, fontWeight: 700 }}
            >
              RETRY
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
