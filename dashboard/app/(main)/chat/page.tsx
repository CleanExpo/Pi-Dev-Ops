// app/(main)/chat/page.tsx — context-aware Claude chat interface
"use client";

import { useState, useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/types";

const SESSION_KEY = "pi-ceo-chat";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SESSION_KEY);
      if (stored) setMessages(JSON.parse(stored) as ChatMessage[]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setError("");

    const userMsg: ChatMessage = { role: "user", content: text, ts: Date.now() / 1000 };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next }),
      });
      if (!res.ok) {
        const d = await res.json() as { error?: string };
        throw new Error(d.error ?? `HTTP ${res.status}`);
      }
      const { reply } = await res.json() as { reply: string };
      const assistantMsg: ChatMessage = { role: "assistant", content: reply, ts: Date.now() / 1000 };
      const final = [...next, assistantMsg];
      setMessages(final);
      localStorage.setItem(SESSION_KEY, JSON.stringify(final.slice(-50)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setMessages([]);
    localStorage.removeItem(SESSION_KEY);
  }

  return (
    <div
      className="flex flex-col flex-1 min-h-0"
      style={{ height: "calc(100vh - 44px)" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 sm:px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Claude Chat
          <span className="hidden sm:inline"> — Pi CEO Engineering Team</span>
        </span>
        <button
          onClick={clearChat}
          className="font-mono text-[10px] transition-colors min-h-[36px] px-2"
          style={{ color: "var(--text-dim)" }}
          onMouseOver={(e) => (e.currentTarget.style.color = "#F87171")}
          onMouseOut={(e) => (e.currentTarget.style.color = "var(--text-dim)")}
        >
          CLEAR
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 sm:px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <p className="font-mono text-xs sm:text-[11px] mt-6 sm:mt-8 leading-relaxed" style={{ color: "var(--text-dim)" }}>
            Ask anything about the codebase, architecture, or how to proceed.
            <br />
            e.g. &quot;Explain the authentication flow&quot; or &quot;Start building sprint 1&quot;
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 sm:gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <span
              className="font-mono text-[10px] shrink-0 mt-1"
              style={{ minWidth: "2.5rem", color: "var(--text-dim)" }}
            >
              {m.role === "user" ? "YOU" : "CEO"}
            </span>
            <div
              className="font-mono text-xs sm:text-[12px] leading-relaxed max-w-[85%] sm:max-w-2xl whitespace-pre-wrap break-words"
              style={{
                color: m.role === "user" ? "var(--text)" : "var(--text)",
                textAlign: m.role === "user" ? "right" : "left",
              }}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-2 sm:gap-3">
            <span className="font-mono text-[10px] mt-1" style={{ color: "var(--text-dim)" }}>CEO</span>
            <span className="font-mono text-xs" style={{ color: "var(--text-dim)" }}>thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="px-3 sm:px-4 py-2 font-mono text-xs" style={{ background: "#1a0808", color: "#F87171" }}>
          ✗ {error}
        </div>
      )}

      {/* Input */}
      <div
        className="flex items-end gap-2 px-3 sm:px-4 py-2 shrink-0"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
          }}
          placeholder="Ask the engineering team… (Enter to send, Shift+Enter for newline)"
          rows={2}
          className="flex-1 font-mono text-xs sm:text-[12px] border-0 outline-none resize-none px-3 py-2"
          style={{
            background: "var(--panel)",
            color: "var(--text)",
            border: "1px solid var(--border)",
            minHeight: "60px",
          }}
        />
        <button
          onClick={() => void send()}
          disabled={loading || !input.trim()}
          className="font-mono text-xs px-4 disabled:opacity-30 transition-opacity shrink-0"
          style={{
            background: "var(--accent)",
            color: "#FFFFFF",
            fontWeight: 700,
            minHeight: "44px",
          }}
        >
          SEND
        </button>
      </div>
    </div>
  );
}
