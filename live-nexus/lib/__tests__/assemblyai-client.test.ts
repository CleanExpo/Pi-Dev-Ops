import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { Server } from "mock-socket";
import { AssemblyAiClient } from "../assemblyai-client";

const WS_URL = "wss://streaming.assemblyai.com/v3/ws";

describe("AssemblyAiClient", () => {
  let server: Server;

  beforeEach(() => {
    server = new Server(WS_URL + "?token=tmp_abc");
  });

  afterEach(() => {
    server.stop();
  });

  it("emits partial transcript events from v3 Turn (end_of_turn=false)", async () => {
    const partials: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(
          JSON.stringify({
            type: "Turn",
            turn_order: 0,
            end_of_turn: false,
            transcript: "hello world",
            words: [],
          })
        );
      }, 10);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("partial", (e) => partials.push(e.text));
    client.connect();

    await new Promise((r) => setTimeout(r, 50));
    expect(partials).toContain("hello world");
  });

  it("emits final transcript events from v3 Turn (end_of_turn=true) with speaker_label", async () => {
    const finals: Array<{ text: string; speaker: string }> = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(
          JSON.stringify({
            type: "Turn",
            turn_order: 1,
            end_of_turn: true,
            transcript: "this is final",
            speaker_label: "A",
            words: [
              { text: "this", start: 0, end: 300, confidence: 0.99 },
              { text: "is", start: 350, end: 500, confidence: 0.98 },
              { text: "final", start: 550, end: 1500, confidence: 0.99 },
            ],
          })
        );
      }, 10);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("final", (e) => finals.push({ text: e.text, speaker: e.speaker }));
    client.connect();

    await new Promise((r) => setTimeout(r, 50));
    expect(finals[0]).toEqual({ text: "this is final", speaker: "A" });
  });

  it("emits disconnect event on socket close", async () => {
    const events: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => socket.close(), 10);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("disconnect", () => events.push("disconnect"));
    client.connect();

    await new Promise((r) => setTimeout(r, 50));
    expect(events).toContain("disconnect");
  });

  it("close() prevents further events", async () => {
    const partials: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(
          JSON.stringify({
            type: "Turn",
            turn_order: 0,
            end_of_turn: false,
            transcript: "after close",
            words: [],
          })
        );
      }, 30);
    });

    const client = new AssemblyAiClient({ wsUrl: WS_URL, token: "tmp_abc" });
    client.on("partial", (e) => partials.push(e.text));
    client.connect();
    client.close();

    await new Promise((r) => setTimeout(r, 80));
    expect(partials).not.toContain("after close");
  });
});
