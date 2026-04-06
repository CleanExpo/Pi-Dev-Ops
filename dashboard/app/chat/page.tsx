// app/chat/page.tsx — context-aware Claude chat interface
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

  // Restore chat history from localStorage
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
    <div className="flex flex-col flex-1 min-h-0" style={{ height: "calc(100vh - 40px)" }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid #252525" }}
      >
        <span className="font-mono text-[10px] text-[#999] uppercase tracking-widest">
          Claude Chat — Pi CEO Engineering Team
        </span>
        <button
          onClick={clearChat}
          className="font-mono text-[9px] text-[#777] hover:text-red transition-colors"
        >
          CLEAR
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <p className="font-mono text-[11px] text-[#666] mt-8">
            Ask anything about your codebase, architecture, or how to proceed.
            <br />
            e.g. &quot;Explain the authentication flow&quot; or &quot;Start building sprint 1&quot;
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <span
              className="font-mono text-[9px] text-[#777] shrink-0 mt-1"
              style={{ minWidth: "3rem" }}
            >
              {m.role === "user" ? "YOU" : "CEO"}
            </span>
            <div
              className="font-mono text-[12px] leading-relaxed max-w-2xl whitespace-pre-wrap"
              style={{
                color: m.role === "user" ? "#F0EDE8" : "#CCCCCC",
                textAlign: m.role === "user" ? "right" : "left",
              }}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <span className="font-mono text-[9px] text-[#777] mt-1">CEO</span>
            <span className="font-mono text-[12px] text-[#666]">thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="px-4 py-1.5 font-mono text-[11px] text-red" style={{ background: "#1a0808" }}>
          ✗ {error}
        </div>
      )}

      {/* Input */}
      <div
        className="flex items-center gap-2 px-4 py-2 shrink-0"
        style={{ borderTop: "1px solid #252525" }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
          }}
          placeholder="Ask the engineering team… (Enter to send, Shift+Enter for newline)"
          rows={2}
          className="flex-1 bg-transparent font-mono text-[12px] text-text placeholder:text-[#555] border-0 outline-none resize-none"
        />
        <button
          onClick={() => void send()}
          disabled={loading || !input.trim()}
          className="font-mono text-[11px] px-4 py-1 disabled:opacity-30 transition-colors shrink-0"
          style={{ background: "#E8751A", color: "#0A0A0A", fontWeight: 700 }}
        >
          SEND
        </button>
      </div>
    </div>
  );
}
