// app/(main)/brain/page.tsx — 2nd Brain flywheel status board (always-visible UI)
"use client";

import BrainStatusPanel from "@/components/brain/BrainStatusPanel";

export default function BrainPage() {
  return (
    <div className="flex-1 overflow-auto p-6 md:p-8" style={{ background: "var(--background)" }}>
      <BrainStatusPanel />
    </div>
  );
}
