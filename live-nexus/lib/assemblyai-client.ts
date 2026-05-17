/** Browser-side AssemblyAI realtime WebSocket wrapper.
 * Emits "partial" / "final" / "disconnect" / "error" events. */

export interface PartialEvent {
  text: string;
  words: Array<{ text: string; start: number; end: number; confidence: number }>;
}

export interface FinalEvent {
  text: string;
  speaker: string;
  audioStart: number;
  audioEnd: number;
}

export type AssemblyAiEvents = {
  partial: PartialEvent;
  final: FinalEvent;
  disconnect: { code: number; reason: string };
  error: { message: string };
};

type Listener<K extends keyof AssemblyAiEvents> = (e: AssemblyAiEvents[K]) => void;

export interface AssemblyAiClientOptions {
  wsUrl: string;
  token: string;
}

export class AssemblyAiClient {
  private ws: WebSocket | null = null;
  private listeners: { [K in keyof AssemblyAiEvents]?: Listener<K>[] } = {};
  private closed = false;

  constructor(private opts: AssemblyAiClientOptions) {}

  on<K extends keyof AssemblyAiEvents>(event: K, fn: Listener<K>): void {
    (this.listeners[event] as Listener<K>[] | undefined) ??= [];
    (this.listeners[event] as Listener<K>[]).push(fn);
  }

  private emit<K extends keyof AssemblyAiEvents>(event: K, payload: AssemblyAiEvents[K]): void {
    if (this.closed) return;
    for (const fn of (this.listeners[event] ?? []) as Listener<K>[]) fn(payload);
  }

  connect(): void {
    const url = `${this.opts.wsUrl}?token=${encodeURIComponent(this.opts.token)}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string);
        if (data.message_type === "PartialTranscript") {
          this.emit("partial", { text: data.text, words: data.words ?? [] });
        } else if (data.message_type === "FinalTranscript") {
          this.emit("final", {
            text: data.text,
            speaker: data.speaker ?? "?",
            audioStart: data.audio_start ?? 0,
            audioEnd: data.audio_end ?? 0,
          });
        }
      } catch (e) {
        this.emit("error", { message: `parse error: ${(e as Error).message}` });
      }
    };
    this.ws.onclose = (ev) => {
      this.emit("disconnect", { code: ev.code, reason: ev.reason });
    };
    this.ws.onerror = () => {
      this.emit("error", { message: "WebSocket error" });
    };
  }

  /** Send 16-bit PCM audio chunk to AssemblyAI. */
  sendAudio(chunk: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(chunk);
    }
  }

  close(): void {
    this.closed = true;
    if (this.ws) {
      try {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ terminate_session: true }));
        }
      } catch {
        /* ignore */
      }
      this.ws.close();
      this.ws = null;
    }
  }
}
