import Link from "next/link";

export default function BuildsEmpty() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center px-4 text-center">
      <p className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>No build sessions yet.</p>
      <p className="font-mono text-[10px] mt-2" style={{ color: "var(--text-dim)" }}>
        Sessions start after Linear Ready for Pi-Dev and pi-dev:autonomous, or from Control → Build.
      </p>
      <p className="font-mono text-[10px] mt-3" style={{ color: "var(--text-dim)" }}>
        <Link href="/control/goal" style={{ color: "var(--accent)" }}>Goal → Linear</Link>
        {" · "}
        <Link href="/control/build" style={{ color: "var(--accent)" }}>Run a build</Link>
      </p>
    </div>
  );
}
