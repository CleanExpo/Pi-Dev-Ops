// RA-7898 — a board on a wall screen. Auth-gated by proxy.ts ("/control" prefix).
import { Suspense } from "react";

import KioskBoard from "@/components/boards/KioskBoard";

export const metadata = { title: "Board kiosk · Mission Control" };

export default function Page() {
  return <Suspense><KioskBoard /></Suspense>;
}
