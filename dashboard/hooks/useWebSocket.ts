"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { WS_BASE } from "@/lib/api";
import type { OutputLine } from "@/lib/types";

type WSStatus = "idle" | "connecting" | "connected" | "done" | "error";

export function useWebSocket(sessionId: string | null) {
  const [lines, setLines] = useState<OutputLine[]>([]);
  const [status, setStatus] = useState<WSStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(
    (sid: string) => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      setLines([]);
      setStatus("connecting");

      const ws = new WebSocket(`${WS_BASE}/ws/build/${sid}`);
      wsRef.current = ws;

      ws.onopen = () => setStatus("connected");

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data) as OutputLine & {
            status?: string;
          };
          if (data.type === "done") {
            setStatus("done");
          }
          setLines((prev) => [...prev, data]);
        } catch {
          // non-JSON message; ignore
        }
      };

      ws.onerror = () => setStatus("error");

      ws.onclose = (ev) => {
        if (ev.code === 4001) {
          setStatus("error");
          setLines((prev) => [
            ...prev,
            { type: "error", text: "  Not authenticated — please log in", ts: Date.now() / 1000 },
          ]);
        } else if (status !== "done") {
          setStatus("idle");
        }
      };
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("idle");
  }, []);

  // Auto-connect when sessionId changes
  useEffect(() => {
    if (sessionId) {
      connect(sessionId);
    }
    return () => {
      wsRef.current?.close();
    };
  }, [sessionId, connect]);

  return { lines, status, connect, disconnect };
}
