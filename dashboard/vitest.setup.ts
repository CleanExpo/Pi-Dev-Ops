import "@testing-library/jest-dom";
import { afterEach } from "vitest";

import { resetSources } from "@/lib/boards/sources/poller";

// Node 26 ships its own global localStorage/sessionStorage. Without a backing
// file Node's accessor returns undefined, and it shadows the jsdom Storage that
// the jsdom environment would otherwise expose, so `window.localStorage` is
// undefined in every test. Node 22 has no such global, so the same suite passed
// there. Re-point both names at the jsdom window's own Storage, on every Node
// version, so the tests never depend on which runtime owns the global.
const jsdomWindow = (globalThis as { jsdom?: { window: Window } }).jsdom?.window;
if (jsdomWindow) {
  for (const name of ["localStorage", "sessionStorage"] as const) {
    const storage = jsdomWindow[name];
    for (const target of [globalThis, window]) {
      Object.defineProperty(target, name, {
        configurable: true,
        enumerable: true,
        get: () => storage,
      });
    }
  }
}

// RA-7898: panels share one poller per feed. Drop every poller and cache after
// each case so a per-case fetch stub never sees another case's data.
afterEach(() => {
  resetSources();
});
