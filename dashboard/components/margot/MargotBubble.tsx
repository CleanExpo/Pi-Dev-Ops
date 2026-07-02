"use client";

import Image from "next/image";
import { MessageCircle, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  MARGOT_ACCENT,
  MARGOT_AVATAR_PATH,
  MARGOT_DISPLAY_NAME,
  MARGOT_ROLE_LABEL,
  MARGOT_TENANT_ID,
  MARGOT_WELCOME,
} from "@/lib/margot-surface";

interface BubbleMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

function MargotAvatar({ size = 48 }: { size?: number }) {
  return (
    <Image
      src={MARGOT_AVATAR_PATH}
      alt={`${MARGOT_DISPLAY_NAME} avatar`}
      width={size}
      height={size}
      className="rounded-full object-cover ring-2 ring-white/15"
      priority
    />
  );
}

export default function MargotBubble() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<BubbleMessage[]>([
    { id: "welcome", role: "assistant", text: MARGOT_WELCOME },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId] = useState(`dashboard-${MARGOT_TENANT_ID}`);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/margot/bubble", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, conversation_id: conversationId }),
      });

      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { error?: string };
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: err.error ?? "Margot is temporarily unavailable. Try again shortly.",
          },
        ]);
        return;
      }

      const data = (await res.json()) as { reply?: string };
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: data.reply?.trim() || "No reply received.",
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: "Connection error — check Pi-CEO backend reachability.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed right-4 bottom-20 sm:bottom-6 z-50 flex flex-col items-end gap-3">
      {open && (
        <div
          className="flex w-[min(100vw-2rem,380px)] flex-col overflow-hidden rounded-lg border shadow-2xl"
          style={{
            height: "min(480px, calc(100vh - 7rem))",
            background: "var(--panel)",
            borderColor: "var(--border)",
          }}
        >
          <div
            className="flex items-center justify-between gap-2 border-b px-4 py-3"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="flex min-w-0 items-center gap-3">
              <MargotAvatar size={40} />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {MARGOT_DISPLAY_NAME}
                </p>
                <p className="truncate text-xs" style={{ color: "var(--text-muted)" }}>
                  {MARGOT_ROLE_LABEL}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md p-2 transition-colors hover:opacity-80"
              style={{ color: "var(--text-muted)" }}
              aria-label="Close Margot"
            >
              <X size={16} />
            </button>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className="max-w-[88%] rounded-lg px-3 py-2 text-sm leading-relaxed"
                  style={{
                    background:
                      msg.role === "user" ? MARGOT_ACCENT : "var(--panel-hover)",
                    color: msg.role === "user" ? "#fff" : "var(--text)",
                  }}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            {loading && (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                Margot is thinking…
              </p>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t px-3 py-3" style={{ borderColor: "var(--border)" }}>
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder="Ask Margot about portfolio ops…"
                className="min-w-0 flex-1 rounded-md border px-3 py-2 text-sm outline-none"
                style={{
                  background: "var(--background)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => void sendMessage()}
                disabled={!input.trim() || loading}
                className="flex h-9 w-9 items-center justify-center rounded-md text-white disabled:opacity-40"
                style={{ background: MARGOT_ACCENT }}
                aria-label="Send"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-14 w-14 items-center justify-center rounded-full transition-transform hover:scale-105"
        style={{ boxShadow: `0 8px 28px ${MARGOT_ACCENT}55` }}
        aria-label={open ? "Close Margot" : "Open Margot personal assistant"}
      >
        {open ? (
          <span
            className="flex h-14 w-14 items-center justify-center rounded-full text-white"
            style={{ background: MARGOT_ACCENT }}
          >
            <X size={22} />
          </span>
        ) : (
          <>
            <MargotAvatar size={56} />
            <span
              className="absolute -right-0.5 -bottom-0.5 flex h-5 w-5 items-center justify-center rounded-full text-white ring-2 ring-[var(--background)]"
              style={{ background: MARGOT_ACCENT }}
              aria-hidden
            >
              <MessageCircle size={11} />
            </span>
          </>
        )}
      </button>
    </div>
  );
}
