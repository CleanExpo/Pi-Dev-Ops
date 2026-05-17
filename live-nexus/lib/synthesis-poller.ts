import type { Action } from "./markdown-composer";

export interface SynthesisPollerOptions {
  intervalMs: number;
  getState: () => { transcript: string; topics: string[]; actions: Action[] };
  onUpdate: (update: { topics: string[]; actions: Action[] }) => void;
  onPause?: () => void;
  onResume?: () => void;
}

const FAIL_PAUSE_THRESHOLD = 3;

export class SynthesisPoller {
  private timer: ReturnType<typeof setInterval> | null = null;
  private stopped = false;
  private consecutiveFailures = 0;
  private paused = false;

  constructor(private opts: SynthesisPollerOptions) {}

  start(): void {
    this.stopped = false;
    this.timer = setInterval(() => void this.tick(), this.opts.intervalMs);
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  /** Force an immediate poll, bypassing the interval. */
  async flush(): Promise<void> {
    await this.tick();
  }

  private async tick(): Promise<void> {
    if (this.stopped) return;
    const state = this.opts.getState();
    try {
      const res = await fetch("/api/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: state.transcript,
          current_topics: state.topics,
          current_actions: state.actions,
        }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = (await res.json()) as { topics: string[]; actions: Action[] };
      if (this.stopped) return;
      this.consecutiveFailures = 0;
      if (this.paused) {
        this.paused = false;
        this.opts.onResume?.();
      }
      this.opts.onUpdate(data);
    } catch (e) {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= FAIL_PAUSE_THRESHOLD && !this.paused) {
        this.paused = true;
        this.opts.onPause?.();
      }
      console.warn("[synthesis-poller] tick failed:", e);
    }
  }
}
