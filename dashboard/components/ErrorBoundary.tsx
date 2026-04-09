// components/ErrorBoundary.tsx — React error boundary with Bloomberg aesthetic
"use client";

import { Component, type ReactNode } from "react";

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
          className="flex flex-col items-center justify-center h-full px-8 py-12 font-mono"
          style={{ background: "#0A0A0A", color: "#F0EDE8" }}
        >
          <div
            className="w-full max-w-md p-6"
            style={{ border: "1px solid #F87171", background: "#1a0808" }}
          >
            <div className="flex items-center gap-2 mb-4">
              <span className="text-[14px]" style={{ color: "#F87171" }}>✗</span>
              <span className="text-[11px] uppercase tracking-widest" style={{ color: "#F87171" }}>
                Component Error
              </span>
            </div>
            <p className="text-[11px] mb-4 leading-relaxed" style={{ color: "#C8C5C0" }}>
              {this.state.error.message}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="font-mono text-[10px] px-4 py-1.5 tracking-wider"
              style={{ background: "#E8751A", color: "#FFF", fontWeight: 700 }}
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
