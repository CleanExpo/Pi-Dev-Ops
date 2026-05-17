import { test, expect } from "@playwright/test";

test("landing page renders brand chrome and preflight", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("UNITE GROUP NEXUS")).toBeVisible();
  await expect(page.getByText("Live meeting notes")).toBeVisible();
  // Pre-flight checklist row (exact match — there's also a paragraph below mentioning microphone access)
  await expect(page.getByText("Microphone", { exact: true })).toBeVisible();
});

test("start button redirects to /m/[uuid]", async ({ page, context }) => {
  await context.grantPermissions(["microphone"]);
  // Stub /api/session to return ok so preflight passes
  await page.route("**/api/session", (route) =>
    route.fulfill({
      status: 200,
      body: JSON.stringify({
        token: "x",
        ws_url: "wss://x",
        expires_at: Date.now() + 60000,
      }),
    })
  );
  await page.goto("/");
  // Wait for preflight to settle
  await page.waitForTimeout(800);
  const startButton = page.locator("button:has-text('Start Meeting')");
  await expect(startButton).toBeEnabled({ timeout: 5000 });
  await startButton.click();
  await expect(page).toHaveURL(/\/m\/[\w-]+/);
  await expect(page.getByText("UNITE GROUP NEXUS")).toBeVisible();
});

test("ending a meeting synthesizes latest transcript before saving", async ({ page, context }) => {
  await context.grantPermissions(["microphone"]);

  await page.addInitScript(() => {
    const makeStream = () => {
      const AudioCtor = window.AudioContext;
      const audioContext = new AudioCtor({ sampleRate: 16000 });
      const oscillator = audioContext.createOscillator();
      const destination = audioContext.createMediaStreamDestination();
      oscillator.connect(destination);
      oscillator.start();
      return destination.stream;
    };

    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => makeStream(),
        enumerateDevices: async () => [
          { kind: "audioinput", label: "Test microphone", deviceId: "test-mic" },
        ],
      },
    });

    const NativeWebSocket = window.WebSocket;

    class MockAssemblyWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      readyState = MockAssemblyWebSocket.CONNECTING;
      onopen: ((this: WebSocket, event: Event) => void) | null = null;
      onmessage: ((this: WebSocket, event: MessageEvent) => void) | null = null;
      onclose: ((this: WebSocket, event: CloseEvent) => void) | null = null;
      private listeners: Record<string, EventListener[]> = {};

      constructor() {
        setTimeout(() => {
          this.readyState = MockAssemblyWebSocket.OPEN;
          const openEvent = new Event("open");
          this.onopen?.call(this as unknown as WebSocket, openEvent);
          this.listeners.open?.forEach((listener) => listener(openEvent));
          const messageEvent = new MessageEvent("message", {
            data: JSON.stringify({
              type: "Turn",
              transcript: "Pricing proposal for RestoreAssist and Q2 numbers update.",
              speaker_label: "A",
              end_of_turn: true,
              words: [{ start: 1000, end: 2500 }],
            })
          });
          this.onmessage?.call(this as unknown as WebSocket, messageEvent);
          this.listeners.message?.forEach((listener) => listener(messageEvent));
        }, 50);
      }

      send() {}

      close() {
        this.readyState = MockAssemblyWebSocket.CLOSED;
        const closeEvent = new CloseEvent("close");
        this.onclose?.call(this as unknown as WebSocket, closeEvent);
        this.listeners.close?.forEach((listener) => listener(closeEvent));
      }

      addEventListener(type: string, listener: EventListener) {
        this.listeners[type] ??= [];
        this.listeners[type].push(listener);
      }

      removeEventListener(type: string, listener: EventListener) {
        this.listeners[type] = (this.listeners[type] ?? []).filter((item) => item !== listener);
      }
    }

    function WebSocketShim(url: string | URL, protocols?: string | string[]) {
      if (String(url).includes("mock.assemblyai.local")) {
        return new MockAssemblyWebSocket() as unknown as WebSocket;
      }
      return new NativeWebSocket(url, protocols);
    }

    WebSocketShim.CONNECTING = NativeWebSocket.CONNECTING;
    WebSocketShim.OPEN = NativeWebSocket.OPEN;
    WebSocketShim.CLOSING = NativeWebSocket.CLOSING;
    WebSocketShim.CLOSED = NativeWebSocket.CLOSED;
    WebSocketShim.prototype = NativeWebSocket.prototype;

    window.WebSocket = WebSocketShim as unknown as typeof WebSocket;
  });

  await page.route("**/api/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        token: "x",
        ws_url: "wss://mock.assemblyai.local/v3/ws",
        expires_at: Date.now() + 60000,
      }),
    })
  );

  let synthesisBody: Record<string, unknown> | null = null;
  await page.route("**/api/synthesize", async (route) => {
    synthesisBody = route.request().postDataJSON();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        topics: ["RestoreAssist pricing proposal", "Q2 numbers update"],
        actions: [
          {
            title: "Prepare RestoreAssist pricing proposal",
            description: "Prepare the RestoreAssist pricing proposal with updated Q2 numbers.",
            priority: 2,
          },
        ],
      }),
    });
  });

  let saveBody: Record<string, unknown> | null = null;
  await page.route("**/api/save", async (route) => {
    saveBody = route.request().postDataJSON();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        fileId: "test-file",
        driveUrl: "https://drive.google.com/file/d/test-file/view",
      }),
    });
  });

  await page.goto("/m/e2e-final-synthesis");
  const startButton = page.getByRole("button", { name: /Start Meeting/i });
  await expect(startButton).toBeEnabled();
  await page.waitForTimeout(800);
  await startButton.click();
  await expect(page.getByText("Pricing proposal for RestoreAssist")).toBeVisible();
  await page.getByRole("button", { name: /End Meeting/i }).click();
  await expect(page.getByRole("link", { name: /Open in Drive/i })).toBeVisible();

  const finalSynthesisBody = synthesisBody as { transcript?: string } | null;
  const finalSaveBody = saveBody as { topics?: string[]; actions?: unknown[] } | null;

  expect(finalSynthesisBody?.transcript).toContain("Pricing proposal for RestoreAssist");
  expect(finalSaveBody?.topics).toContain("RestoreAssist pricing proposal");
  expect(JSON.stringify(finalSaveBody?.actions)).toContain(
    "Prepare RestoreAssist pricing proposal"
  );
});
