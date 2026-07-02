// MargotAssetsPanel.tsx — Mission Control Margot asset preview (dry-run + packets).
"use client";

import { useCallback, useEffect, useState } from "react";

const API = "/api/pi-ceo/api/margot/assets";

interface OptionsData {
  schema_version?: number;
  canonical_name?: string;
  model?: string;
  canonical_asset_exists?: boolean;
  projects?: string[];
  variants?: string[];
  matrix_item_count?: number;
  error?: string;
}

interface PreviewData {
  project?: string;
  variant?: string;
  payload?: { model?: string; prompt?: string; size?: string; quality?: string };
  provenance?: { prompt_sha256?: string };
  error?: string;
}

interface PacketRow {
  filename: string;
  modified_at: string;
  item_count: number;
  mode: string;
}

interface GeneratedRow {
  filename: string;
  modified_at: string;
  size_bytes: number;
  has_provenance: boolean;
}

function fmtAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "?";
  if (ms < 60_000) return `${Math.floor(ms / 1_000)}s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  return `${Math.floor(ms / 3_600_000)}h ago`;
}

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include", cache: "no-store" });
  const body = (await r.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!r.ok && !body.error) {
    return { ...body, error: body.detail ?? `HTTP ${r.status}` } as T;
  }
  return body;
}

export default function MargotAssetsPanel() {
  const [options, setOptions] = useState<OptionsData | null>(null);
  const [project, setProject] = useState("unite-group");
  const [variant, setVariant] = useState("avatar");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [packets, setPackets] = useState<PacketRow[]>([]);
  const [generated, setGenerated] = useState<GeneratedRow[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [buildLoading, setBuildLoading] = useState(false);
  const [buildResult, setBuildResult] = useState<{ filename?: string; item_count?: number; error?: string } | null>(null);
  const [expandedPacket, setExpandedPacket] = useState<string | null>(null);
  const [packetDetail, setPacketDetail] = useState<{ item_count?: number; items?: Array<{ project: string; variant: string }> } | null>(null);

  const refreshMeta = useCallback(async () => {
    const [opts, pkt, gen] = await Promise.all([
      getJSON<OptionsData>(`${API}/options`),
      getJSON<{ packets?: PacketRow[] }>(`${API}/packets?limit=8`),
      getJSON<{ assets?: GeneratedRow[] }>(`${API}/generated?limit=6`),
    ]);
    setOptions(opts);
    setPackets(pkt.packets ?? []);
    setGenerated(gen.assets ?? []);
  }, []);

  useEffect(() => {
    void refreshMeta();
  }, [refreshMeta]);

  useEffect(() => {
    if (options?.projects?.length && !options.projects.includes(project)) {
      setProject(options.projects[0]);
    }
    if (options?.variants?.length && !options.variants.includes(variant)) {
      setVariant(options.variants[0]);
    }
  }, [options, project, variant]);

  const runPreview = async () => {
    setPreviewLoading(true);
    setPreview(null);
    const qs = new URLSearchParams({ project, variant });
    if (notes.trim()) qs.set("notes", notes.trim());
    const data = await getJSON<PreviewData>(`${API}/preview?${qs}`);
    setPreview(data);
    setPreviewLoading(false);
  };

  const runBuildPacket = async () => {
    setBuildLoading(true);
    setBuildResult(null);
    try {
      const r = await fetch(`${API}/packets`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes.trim() || undefined }),
      });
      const data = (await r.json().catch(() => ({}))) as {
        filename?: string;
        item_count?: number;
        error?: string;
        detail?: string;
      };
      if (!r.ok) {
        setBuildResult({ error: data.detail ?? data.error ?? `HTTP ${r.status}` });
      } else {
        setBuildResult({ filename: data.filename, item_count: data.item_count });
        void refreshMeta();
      }
    } catch (exc) {
      setBuildResult({ error: String(exc) });
    }
    setBuildLoading(false);
  };

  const togglePacket = async (filename: string) => {
    if (expandedPacket === filename) {
      setExpandedPacket(null);
      setPacketDetail(null);
      return;
    }
    setExpandedPacket(filename);
    const data = await getJSON<{ item_count?: number; items?: Array<{ project: string; variant: string }> }>(
      `${API}/packets/${encodeURIComponent(filename)}`,
    );
    setPacketDetail(data);
  };

  return (
    <section
      className="flex flex-col h-full min-h-0"
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        borderRadius: 8,
      }}
      aria-label="Margot asset preview"
    >
      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-sm font-semibold tracking-tight">Margot Assets</h2>
        <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
          {options?.model ?? "—"} · {options?.matrix_item_count ?? "?"} matrix items · dry-run default
        </span>
      </header>

      <div className="flex-1 overflow-auto p-4 flex flex-col gap-4 text-xs">
        {options?.error && (
          <p style={{ color: "var(--error)" }}>⚠ {options.error}</p>
        )}

        {options && !options.error && (
          <p style={{ color: "var(--text-dim)" }}>
            Canonical asset{" "}
            {options.canonical_asset_exists ? (
              <span style={{ color: "var(--success, #22c55e)" }}>present</span>
            ) : (
              <span style={{ color: "var(--warning)" }}>missing locally</span>
            )}
            {" · "}
            {options.projects?.length ?? 0} projects × {options.variants?.length ?? 0} variants
          </p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <label className="flex flex-col gap-1">
            <span style={{ color: "var(--text-muted)" }}>Project</span>
            <select
              className="rounded border px-2 py-1.5 bg-transparent"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              {(options?.projects ?? [project]).map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span style={{ color: "var(--text-muted)" }}>Variant</span>
            <select
              className="rounded border px-2 py-1.5 bg-transparent"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              value={variant}
              onChange={(e) => setVariant(e.target.value)}
            >
              {(options?.variants ?? [variant]).map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-1">
            <span style={{ color: "var(--text-muted)" }}>Notes (optional)</span>
            <input
              className="rounded border px-2 py-1.5 bg-transparent"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. navy accents"
              maxLength={500}
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded px-3 py-1.5 font-medium"
            style={{ background: "var(--accent)", color: "var(--on-accent)" }}
            disabled={previewLoading}
            onClick={() => { void runPreview(); }}
          >
            {previewLoading ? "Previewing…" : "Preview prompt"}
          </button>
          <button
            type="button"
            className="rounded px-3 py-1.5 font-medium border"
            style={{ borderColor: "var(--border)", color: "var(--text)" }}
            disabled={buildLoading}
            onClick={() => { void runBuildPacket(); }}
          >
            {buildLoading ? "Building packet…" : `Build full packet (${options?.matrix_item_count ?? 28})`}
          </button>
        </div>

        {buildResult?.error && (
          <p style={{ color: "var(--error)" }}>Build failed: {buildResult.error}</p>
        )}
        {buildResult?.filename && (
          <p style={{ color: "var(--success, #22c55e)" }}>
            ✓ Wrote {buildResult.filename} ({buildResult.item_count} items)
          </p>
        )}

        {preview?.payload?.prompt && (
          <div
            className="rounded border p-3 font-mono text-[11px] whitespace-pre-wrap max-h-48 overflow-auto"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          >
            <div className="mb-2" style={{ color: "var(--text-muted)" }}>
              {preview.payload.model} · {preview.payload.size} · sha256{" "}
              {preview.provenance?.prompt_sha256?.slice(0, 12)}…
            </div>
            {preview.payload.prompt}
          </div>
        )}

        {packets.length > 0 && (
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
              Build packets
            </h3>
            <ul className="flex flex-col gap-1">
              {packets.map((p) => (
                <li key={p.filename}>
                  <button
                    type="button"
                    className="w-full text-left rounded border px-2 py-1.5"
                    style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                    onClick={() => { void togglePacket(p.filename); }}
                  >
                    <span className="font-mono" style={{ color: "var(--accent)" }}>{p.filename}</span>
                    <span className="ml-2" style={{ color: "var(--text-dim)" }}>
                      {p.item_count} items · {fmtAge(p.modified_at)}
                    </span>
                  </button>
                  {expandedPacket === p.filename && packetDetail?.items && (
                    <div className="mt-1 ml-2 flex flex-wrap gap-1">
                      {packetDetail.items.map((item) => (
                        <span
                          key={`${item.project}-${item.variant}`}
                          className="rounded px-1.5 py-0.5 text-[10px]"
                          style={{ background: "var(--background)", color: "var(--text-dim)" }}
                        >
                          {item.project}/{item.variant}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {generated.length > 0 && (
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
              Generated assets
            </h3>
            <ul className="flex flex-col gap-1" style={{ color: "var(--text-dim)" }}>
              {generated.map((a) => (
                <li key={a.filename} className="font-mono text-[10px]">
                  {a.filename} · {(a.size_bytes / 1024).toFixed(1)} KB · {fmtAge(a.modified_at)}
                  {a.has_provenance ? " · provenance ✓" : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
