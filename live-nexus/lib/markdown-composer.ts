export interface TranscriptLine {
  timestamp: string; // "14:28"
  speaker: string; // "A" / "B" / "?"
  text: string;
}

export interface Action {
  title: string;
  description: string;
  owner?: string;
  priority: number; // 0..4 Linear scale
}

export interface MeetingState {
  meetingId: string;
  title: string;
  startedAt: string; // ISO
  endedAt: string; // ISO
  brand: string;
  transcript: TranscriptLine[];
  topics: string[];
  actions: Action[];
}

function formatDurationHuman(startISO: string, endISO: string): string {
  const ms = new Date(endISO).getTime() - new Date(startISO).getTime();
  const totalS = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(totalS / 3600);
  const m = Math.floor((totalS % 3600) / 60);
  const s = totalS % 60;
  if (h) return `${h}h${String(m).padStart(2, "0")}m${String(s).padStart(2, "0")}s`;
  if (m) return `${m}m${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

function dateOnly(iso: string): string {
  return iso.slice(0, 10);
}

export function composeMeetingMarkdown(state: MeetingState): string {
  const title = state.title.trim() || "Meeting";
  const dateStr = dateOnly(state.startedAt);

  const fm = [
    "---",
    "type: live-meeting",
    `meeting_id: ${state.meetingId}`,
    `started_at: ${state.startedAt}`,
    `ended_at: ${state.endedAt}`,
    `duration_human: ${formatDurationHuman(state.startedAt, state.endedAt)}`,
    "source: live-nexus",
    `brand: ${state.brand}`,
    "---",
  ].join("\n");

  const heading = `# ${title} — ${dateStr}`;

  const topicsSection =
    "## Topics Discussed\n" +
    (state.topics.length ? state.topics.map((t) => `- ${t}`).join("\n") : "_(none)_");

  const actionsSection =
    "## Action Items\n" +
    (state.actions.length
      ? state.actions
          .map((a) => {
            const parts = [a.title];
            if (a.description) parts.push(a.description);
            if (a.owner) parts.push(a.owner);
            return `- [ ] ${parts.join(" — ")}`;
          })
          .join("\n")
      : "_(none)_");

  const transcriptSection =
    "## Transcript\n\n" +
    state.transcript
      .map((l) => `[${l.timestamp}] Speaker ${l.speaker}: ${l.text}`)
      .join("\n");

  return [fm, "", heading, "", topicsSection, "", actionsSection, "", transcriptSection, ""].join("\n");
}
