import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { Server } from "mock-socket";
import { AssemblyAiClient } from "../assemblyai-client";

const WS_URL = "wss://api.assemblyai.com/v2/realtime/ws";

describe("AssemblyAiClient", () => {
  let server: Server;

  beforeEach(() => {
    server = new Server(WS_URL + "?token=tmp_abc");
  });

  afterEach(() => {
    server.stop();
  });

  it("emits partial transcript events", async () => {
    const partials: string[] = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(
          JSON.stringify({
            message_type: "PartialTranscript",
            text: "hello world",
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

  it("emits final transcript events with speaker", async () => {
    const finals: Array<{ text: string; speaker: string }> = [];
    server.on("connection", (socket) => {
      setTimeout(() => {
        socket.send(
          JSON.stringify({
            message_type: "FinalTranscript",
            text: "this is final",
            speaker: "A",
            audio_start: 0,
            audio_end: 1500,
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
          JSON.stringify({ message_type: "PartialTranscript", text: "after close", words: [] })
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
