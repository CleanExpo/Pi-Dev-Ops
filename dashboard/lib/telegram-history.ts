type Role = "user" | "assistant";
export interface Turn { role: Role; content: string }

// ── Conversation history ──────────────────────────────────────────────────────

const HISTORY = new Map<number, Turn[]>();
const MAX_HISTORY_TURNS = 20;

export function getHistory(chatId: number): Turn[] {
  return HISTORY.get(chatId) ?? [];
}

export function pushHistory(chatId: number, role: Role, content: string): void {
  const h = getHistory(chatId);
  h.push({ role, content });
  if (h.length > MAX_HISTORY_TURNS) h.splice(0, h.length - MAX_HISTORY_TURNS);
  HISTORY.set(chatId, h);
}

export function clearHistory(chatId: number): void {
  HISTORY.delete(chatId);
}

// ── Telegram send ─────────────────────────────────────────────────────────────
