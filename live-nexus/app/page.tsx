"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PreflightCheck, type CheckState } from "@/components/PreflightCheck";

function uuidv4(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  arr[6] = (arr[6] & 0x0f) | 0x40;
  arr[8] = (arr[8] & 0x3f) | 0x80;
  const hex = Array.from(arr).map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export default function LandingPage() {
  const router = useRouter();
  const [mic, setMic] = useState<CheckState>("pending");
  const [network, setNetwork] = useState<CheckState>("pending");
  const [browser, setBrowser] = useState<CheckState>("pending");

  useEffect(() => {
    const supportsMedia =
      typeof navigator !== "undefined" &&
      !!navigator.mediaDevices?.getUserMedia &&
      !!window.WebSocket;
    setBrowser(supportsMedia ? "ok" : "fail");

    navigator.mediaDevices
      ?.enumerateDevices()
      .then((devices) => {
        const hasMic = devices.some((d) => d.kind === "audioinput");
        setMic(hasMic ? "ok" : "fail");
      })
      .catch(() => setMic("fail"));

    fetch("/api/session", { method: "POST" })
      .then((res) => setNetwork(res.ok ? "ok" : "fail"))
      .catch(() => setNetwork("fail"));
  }, []);

  const allOk = mic === "ok" && network === "ok" && browser === "ok";

  const start = () => {
    const id = uuidv4();
    router.push(`/m/${id}`);
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-8 px-6">
      <header className="text-center">
        <h1 className="font-brand text-3xl italic">UNITE GROUP NEXUS</h1>
        <p className="mt-2 text-ink-muted">Live meeting notes</p>
      </header>

      <button
        type="button"
        onClick={start}
        disabled={!allOk}
        className="rounded-lg border-2 border-accent bg-accent/10 px-12 py-6 text-lg uppercase tracking-wider text-ink transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        ● Start Meeting
      </button>

      <PreflightCheck mic={mic} network={network} browser={browser} />

      <p className="max-w-md text-center text-sm text-ink-muted">
        Microphone access required. Recording stays on this device until you click End Meeting.
      </p>
    </main>
  );
}
