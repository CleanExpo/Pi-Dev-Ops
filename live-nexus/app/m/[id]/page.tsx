"use client";

import { useEffect, useRef, useState, use } from "react";
import { MeetingHeader, type MeetingHeaderState } from "@/components/MeetingHeader";
import { TranscriptStream } from "@/components/TranscriptStream";
import { SynthesisSidebar } from "@/components/SynthesisSidebar";
import { ConnectionStatus, type ConnectionState } from "@/components/ConnectionStatus";
import { AssemblyAiClient } from "@/lib/assemblyai-client";
import { SynthesisPoller } from "@/lib/synthesis-poller";
import { saveSession, clearSession } from "@/lib/indexeddb-session";
import type { Action, TranscriptLine } from "@/lib/markdown-composer";

const SYNTHESIS_INTERVAL_MS = 30_000;

export default function MeetingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [headerState, setHeaderState] = useState<MeetingHeaderState>("preflight");
  const [connection, setConnection] = useState<ConnectionState>("connected");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [partial, setPartial] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [synthesisPaused, setSynthesisPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [clockTime, setClockTime] = useState("");
  const [endedFileUrl, setEndedFileUrl] = useState<string | null>(null);

  const startedAtRef = useRef<string>("");
  const aaiRef = useRef<AssemblyAiClient | null>(null);
  const pollerRef = useRef<SynthesisPoller | null>(null);

  function fmtClock(d: Date) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  function fmtTs(ms: number) {
    const totalS = Math.floor(ms / 1000);
    const m = Math.floor(totalS / 60);
    const s = totalS % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  useEffect(() => {
    setClockTime(fmtClock(new Date()));
    const i = setInterval(() => {
      setClockTime(fmtClock(new Date()));
      setElapsed((e) => (headerState === "recording" ? e + 1 : e));
    }, 1000);
    return () => clearInterval(i);
  }, [headerState]);

  async function startMeeting() {
    try {
      const sessionRes = await fetch("/api/session", { method: "POST" });
      if (!sessionRes.ok) throw new Error("Failed to mint AssemblyAI token");
      const { token, ws_url } = (await sessionRes.json()) as {
        token: string;
        ws_url: string;
      };

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      const aai = new AssemblyAiClient({ wsUrl: ws_url, token });
      aaiRef.current = aai;
      aai.on("partial", (e) => setPartial(e.text));
      aai.on("final", (e) => {
        setPartial("");
        setLines((prev) => [
          ...prev,
          { timestamp: fmtTs(e.audioStart), speaker: e.speaker, text: e.text },
        ]);
      });
      aai.on("disconnect", () => setConnection("reconnecting"));
      aai.on("error", () => setConnection("error"));
      aai.connect();

      const audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(audioContext.destination);
      processor.onaudioprocess = (ev) => {
        const f32 = ev.inputBuffer.getChannelData(0);
        const i16 = new Int16Array(f32.length);
        for (let i = 0; i < f32.length; i++) {
          const v = Math.max(-1, Math.min(1, f32[i]));
          i16[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
        }
        aai.sendAudio(i16.buffer);
      };

      const poller = new SynthesisPoller({
        intervalMs: SYNTHESIS_INTERVAL_MS,
        getState: () => ({
          transcript: lines.map((l) => `[${l.timestamp}] ${l.speaker}: ${l.text}`).join("\n"),
          topics,
          actions,
        }),
        onUpdate: ({ topics: newT, actions: newA }) => {
          setTopics(newT);
          setActions(newA);
        },
        onPause: () => setSynthesisPaused(true),
        onResume: () => setSynthesisPaused(false),
      });
      pollerRef.current = poller;
      poller.start();

      startedAtRef.current = new Date().toISOString();
      setHeaderState("recording");
    } catch (e) {
      console.error("startMeeting failed:", e);
      setConnection("error");
    }
  }

  async function endMeeting() {
    pollerRef.current?.stop();
    await pollerRef.current?.flush();
    aaiRef.current?.close();
    setHeaderState("ended");

    try {
      const res = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meetingId: id,
          title: topics[0] ?? "Meeting",
          startedAt: startedAtRef.current,
          endedAt: new Date().toISOString(),
          transcript: lines,
          topics,
          actions,
          brand: "unite-group",
        }),
      });
      if (!res.ok) throw new Error("save failed");
      const data = (await res.json()) as { driveUrl: string };
      setEndedFileUrl(data.driveUrl);
      await clearSession();
    } catch (e) {
      console.error("save failed:", e);
      setConnection("error");
    }
  }

  useEffect(() => {
    if (headerState !== "recording") return;
    const i = setInterval(() => {
      void saveSession({
        meetingId: id,
        title: topics[0] ?? "Meeting",
        startedAt: startedAtRef.current,
        endedAt: "",
        transcript: lines,
        topics,
        actions,
        brand: "unite-group",
        lastUpdated: Date.now(),
      });
    }, 5000);
    return () => clearInterval(i);
  }, [headerState, id, lines, topics, actions]);

  return (
    <main className="flex h-screen flex-col">
      <MeetingHeader state={headerState} elapsedSeconds={elapsed} clockTime={clockTime} />
      <ConnectionStatus state={connection} />

      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        <div className="basis-[60%]">
          <TranscriptStream lines={lines} partial={partial} />
        </div>
        <div className="basis-[40%]">
          <SynthesisSidebar
            topics={topics}
            actions={actions}
            synthesisPaused={synthesisPaused}
          />
        </div>
      </div>

      <footer className="flex items-center justify-between border-t border-hairline px-6 py-3 text-xs text-ink-muted">
        <span>● {connection === "connected" ? "Connected" : connection}</span>
        {headerState !== "recording" && headerState !== "ended" && (
          <button
            onClick={startMeeting}
            className="rounded border border-accent px-4 py-2 text-ink hover:bg-accent/10"
          >
            ● Start Meeting
          </button>
        )}
        {headerState === "recording" && (
          <button
            onClick={endMeeting}
            className="rounded border border-accent px-4 py-2 text-ink hover:bg-accent/10"
          >
            End Meeting
          </button>
        )}
        {headerState === "ended" && endedFileUrl && (
          <a
            href={endedFileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded border border-accent px-4 py-2 text-ink hover:bg-accent/10"
          >
            Open in Drive
          </a>
        )}
      </footer>
    </main>
  );
}
