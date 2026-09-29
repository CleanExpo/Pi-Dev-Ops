/**
 * Fire-and-forget: reports errors loudly but never throws, so callers do not fail.
 */
export async function sendEmail(payload: { to: string; subject: string }): Promise<void> {
  const key = process.env.RESEND_API_KEY;
  if (!key) {
    console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);
    return;
  }
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { authorization: `Bearer ${key}` },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) console.error("[notify] non-2xx", res.status);
  } catch (e) {
    console.error("[notify] send failed", e);
  }
}

export async function runWatchdog(problems: string[]) {
  let alerted = false;
  const to = process.env.ALERT_EMAIL?.trim();
  if (to) {
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
  }
  return { healthy: problems.length === 0, alerted };
}
