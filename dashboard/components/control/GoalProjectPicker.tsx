"use client";

import { useEffect, useState } from "react";
import styles from "./control-deck.module.css";

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

  async function reload() {
    const res = await fetch("/api/pi-ceo/api/goal-projects");
    const data = (await res.json().catch(() => ({}))) as {
      projects?: GoalProject[];
      hint?: string;
      detail?: { hint?: string };
    };
    if (!res.ok || !Array.isArray(data.projects)) {
      throw new Error(data.hint || data.detail?.hint || "Could not load projects.");
    }
    setProjects(data.projects);
  }

  useEffect(() => {
    void reload().catch(() => setError("Could not load projects."));
  }, []);

  async function save() {
    if (saving) return;
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
      onSelect(data.project);
      setDraft(EMPTY);
      setCreating(false);
      await reload();
    } catch {
      setError("Network error — project was not created.");
    } finally {
      setSaving(false);
    }
  }

  const selected = projects.find((p) => p.id === selectedId);

  return (
    <div className={styles.field}>
      <span className={styles.fieldLabel}>Project</span>
      <select
        value={selectedId}
        disabled={disabled || creating}
        onChange={(e) => {
          const next = projects.find((p) => p.id === e.target.value);
          if (next) onSelect(next);
        }}
        className={styles.input}
        aria-label="Project"
      >
        <option value="">Select a project</option>
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
      {!creating ? (
        <button
          type="button"
          onClick={() => setCreating(true)}
          disabled={disabled}
          className={`${styles.ghost} mt-2`}
        >
          Create project
        </button>
      ) : (
        <div className={`${styles.card} mt-3`}>
          {(
            [
              ["title", "Title", 1],
              ["description", "Description", 3],
              ["audience", "Main audience", 2],
              ["problem", "Problem", 2],
              ["users", "Users", 2],
              ["outcomes", "Outcomes", 2],
              ["constraints", "Constraints", 2],
              ["out_of_scope", "Out of scope", 2],
            ] as const
          ).map(([key, label, rows]) => (
            <label key={key} className={styles.field}>
              <span className={styles.fieldLabel}>{label}</span>
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
            <button type="button" onClick={() => void save()} disabled={saving} className={styles.primary}>
              {saving ? "Saving…" : "Save project"}
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
