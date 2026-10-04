import "@testing-library/jest-dom";
import { afterEach } from "vitest";

import { resetSources } from "@/lib/boards/sources/poller";

// RA-7898: panels share one poller per feed. Drop every poller and cache after
// each case so a per-case fetch stub never sees another case's data.
afterEach(() => {
  resetSources();
});
