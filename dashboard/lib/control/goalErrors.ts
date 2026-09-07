export interface FiledTicket {
  identifier: string;
  url: string;
  title: string;
  state: string;
  labels: string[];
}

export interface GoalErrorBody {
  error?: string;
  hint?: string;
  filed?: FiledTicket[];
  tickets?: FiledTicket[];
  failed_title?: string;
  detail?: {
    error?: string;
    fields?: string[];
    hint?: string;
    repo?: string;
    filed?: FiledTicket[];
    tickets?: FiledTicket[];
    failed_title?: string;
  };
}

function isFiled(ticket: FiledTicket | undefined): ticket is FiledTicket {
  return Boolean(ticket?.identifier && ticket.url);
}

export function filedTickets(data: GoalErrorBody): FiledTicket[] {
  const raw = data.filed || data.tickets || data.detail?.filed || data.detail?.tickets || [];
  return raw.filter(isFiled);
}

export function mergeFiled(prev: FiledTicket[], next: FiledTicket[]): FiledTicket[] {
  const seen = new Set(prev.map((ticket) => ticket.identifier));
  return [...prev, ...next.filter((ticket) => !seen.has(ticket.identifier))];
}

export function markLanded<T extends {
  title: string;
  selected: boolean;
  landed_identifier?: string;
}>(tickets: T[], landed: FiledTicket[]): T[] {
  return tickets.map((ticket) => {
    const match = landed.find((row) => (
      row.identifier && row.title.trim() === ticket.title.trim()
    ));
    if (!match) return ticket;
    return { ...ticket, selected: false, landed_identifier: match.identifier };
  });
}

export function failedTitle(data: GoalErrorBody): string {
  return (data.failed_title || data.detail?.failed_title || "").trim();
}

export function errorMessage(data: GoalErrorBody, status: number): string {
  const detail = data.detail;
  const fields = detail?.fields?.join(", ");
  const failed = failedTitle(data);
  const suffix = failed ? ` Stopped at “${failed}”.` : "";
  return (
    data.hint
    || detail?.hint
    || (fields ? `Missing: ${fields}` : null)
    || detail?.error
    || data.error
    || `Request failed (${status})`
  ) + suffix;
}
