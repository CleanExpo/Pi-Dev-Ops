"use client";

import { useEffect, useState } from "react";
import { readyToCreate, remainingHint } from "@/lib/control/goalBrief";
import { TWO_PROJECTS_NOTE } from "@/lib/control/goalCopy";
import { readGoalAnalysis } from "@/lib/control/goalAnalysisStore";
import { readGoalBriefId, writeGoalBriefId } from "@/lib/control/goalProjectStore";
import styles from "./control-deck.module.css";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

export interface GoalProject {
  id: string;
  title: string;
  description: string;
  audience: string;
  problem: string;
  users: string;
  outcomes: string;
  constraints: string;
  out_of_scope: string;
}

interface Props {
  selectedId: string;
  disabled: boolean;
  onSelect: (project: GoalProject) => void;
}

export function stubBrief(id: string, title = ""): GoalProject {
  return {
    id,
    title,
    description: "",
    audience: "",
    problem: "",
    users: "",
    outcomes: "",
    constraints: "",
    out_of_scope: "",
  };
}

const EMPTY: Omit<GoalProject, "id"> = {
  title: "",
  description: "",
  audience: "",
  problem: "",
  users: "",
  outcomes: "",
  constraints: "",
  out_of_scope: "",
};

export default function GoalProjectPicker({ selectedId, disabled, onSelect }: Props) {
  const [projects, setProjects] = useState<GoalProject[]>([]);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [extra, setExtra] = useState(false);

  function choose(project: GoalProject) {
    writeGoalBriefId(project.id);
    onSelect(project);
  }

  async function reload(): Promise<GoalProject[]> {
    // The proxy's placeholder has no `projects` key, so this already threw —
    // but with the generic message. Naming the real cause — lib/pi-ceo-fetch.ts.
    const data = await fetchProxyJSON<{
      projects?: GoalProject[];
      hint?: string;
      detail?: { hint?: string };
    }>("/api/goal-projects");
    if (!data) throw new Error("Pi-CEO backend unreachable.");
    if (!Array.isArray(data.projects)) {
      throw new Error(data.hint || data.detail?.hint || "Could not load project briefs.");
    }
    setProjects(data.projects);
    return data.projects;
  }

  useEffect(() => {
    void reload()
      .then((list) => {
        const wanted = selectedId || readGoalAnalysis()?.project_id || readGoalBriefId();
        const found = list.find((p) => p.id === wanted);
        if (found) onSelect(found);
      })
      .catch(() => setError("Could not load project briefs."))
      .finally(() => setLoading(false));
  }, []);

  const canSave = readyToCreate(draft);

  async function save() {
    if (saving || !canSave) return;
    setError("");
    setSaving(true);
    try {
      const res = await fetch("/api/pi-ceo/api/goal-projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const data = (await res.json().catch(() => ({}))) as {
        project?: GoalProject;
        detail?: { hint?: string };
        hint?: string;
      };
      if (!res.ok || !data.project) {
        setError(data.hint || data.detail?.hint || "Project was not created.");
        return;
      }
      const created = data.project;
      choose(created);
      setProjects((prev) => (prev.some((p) => p.id === created.id) ? prev : [...prev, created]));
      setDraft(EMPTY);
      setCreating(false);
      try {
        await reload();
      } catch {
        setError("Saved. The list did not refresh.");
      }
    } catch {
      setError("Network error — project was not created.");
    } finally {
      setSaving(false);
    }
  }

  const selected = projects.find((p) => p.id === selectedId);

  return (
    <div className={styles.field}>
      <span className={styles.fieldLabel}>Project brief</span>
      <p className={`${styles.note} mb-2`}>{TWO_PROJECTS_NOTE}</p>
      {loading ? <p className={styles.note}>Loading project briefs…</p> : null}
      <select
        value={selectedId}
        disabled={disabled || creating || loading}
        onChange={(e) => {
          const next = projects.find((p) => p.id === e.target.value);
          if (next) choose(next);
        }}
        className={styles.input}
        aria-label="Project brief"
      >
        <option value="">Select a brief</option>
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.title}
          </option>
        ))}
      </select>
      {selected ? (
        <p className={`${styles.note} mt-2 whitespace-pre-wrap`}>
          {selected.description}
          {selected.audience ? `\nAudience: ${selected.audience}` : ""}
        </p>
      ) : null}
      {!loading && !error && projects.length === 0 && !creating ? (
        <p className={`${styles.note} mt-2`}>
          No project briefs yet. Create one here — title, description, and audience are required.
        </p>
      ) : null}
      {!creating ? (
        <button
          type="button"
          onClick={() => setCreating(true)}
          disabled={disabled}
          className={`${styles.ghost} mt-2`}
        >
          Create brief
        </button>
      ) : (
        <div className={`${styles.card} mt-3`}>
          {(
            [
              ["title", "Title — the product name", 1, true],
              ["description", "What this product is", 3, true],
              ["audience", "Who it is for", 2, true],
              ["problem", "Problem", 2, false],
              ["users", "Users", 2, false],
              ["outcomes", "Outcomes", 2, false],
              ["constraints", "Constraints", 2, false],
              ["out_of_scope", "Out of scope", 2, false],
            ] as const
          ).filter(([, , , required]) => required || extra).map(([key, label, rows, required]) => (
            <label key={key} className={styles.field}>
              <span className={styles.fieldLabel}>
                {required ? remainingHint(draft[key], label) : label}
              </span>
              <textarea
                value={draft[key]}
                disabled={saving}
                rows={rows}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                className={styles.input}
              />
            </label>
          ))}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setExtra(!extra)} className={styles.ghost}>
              {extra ? "Fewer fields" : "More context"}
            </button>
            <button type="button" onClick={() => void save()} disabled={saving || !canSave} className={styles.primary}>
              {saving ? "Saving…" : "Save brief"}
            </button>
            <button
              type="button"
              onClick={() => { setCreating(false); setError(""); }}
              disabled={saving}
              className={styles.ghost}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {error ? <p className="mt-2 text-[13px]" style={{ color: "var(--error)" }}>{error}</p> : null}
    </div>
  );
}
