"""Pilot memory layer — Supabase-backed persistence for pause_state,
suggestion records, and suggestion→message links.

Per ADR 002: every query runs inside a tenant context (app.current_tenant_slug
set in Memory.__init__ via set_app_tenant RPC). Per ADR 003: pause_state
helpers and message-link helpers enable editMessageReplyMarkup post-tap state.
Per ADR 004: is_blocked filters 'never'-ruled fingerprints before emission.
"""
import os


def _client():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


class Memory:
    def __init__(self, tenant_slug: str = "phill"):
        self.client = _client()
        self.client.rpc("set_app_tenant", {"slug": tenant_slug}).execute()

    # --- pause_state helpers (ADR 003) ---

    def get_pause_state(self, tenant_slug: str) -> str:
        r = (self.client.table("pilot_preferences")
             .select("pause_state")
             .eq("tenant_slug", tenant_slug)
             .limit(1)
             .execute())
        rows = r.data or []
        return rows[0]["pause_state"] if rows else "active"

    def set_pause_state(self, tenant_slug: str, pause_state: str) -> None:
        """Upsert pause_state for a tenant.

        Uses synthetic fingerprint_pattern '__pause__:<slug>' so this row
        coexists with real preference rows without conflicting on the unique key.
        """
        self.client.table("pilot_preferences").upsert(
            {
                "tenant_slug": tenant_slug,
                "pause_state": pause_state,
                "fingerprint_pattern": f"__pause__:{tenant_slug}",
                "rule": "never",
            },
            on_conflict="tenant_slug,fingerprint_pattern",
        ).execute()

    # --- message-link helpers (ADR 003 editMessageReplyMarkup) ---

    def record_message(self, *, suggestion_id: int, chat_id: int,
                       message_id: int, tenant_slug: str) -> None:
        self.client.table("pilot_suggestion_messages").insert({
            "suggestion_id": suggestion_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "tenant_slug": tenant_slug,
        }).execute()

    def get_message_for_suggestion(self, suggestion_id: int) -> dict | None:
        r = (self.client.table("pilot_suggestion_messages")
             .select("chat_id,message_id")
             .eq("suggestion_id", suggestion_id)
             .limit(1)
             .execute())
        rows = r.data or []
        return rows[0] if rows else None

    # --- block-list helper (ADR 004 §2) ---

    def is_blocked(self, fingerprint: str, tenant_slug: str) -> bool:
        """True if a 'never' rule matches this fingerprint for this tenant."""
        r = (self.client.table("pilot_preferences")
             .select("rule")
             .eq("tenant_slug", tenant_slug)
             .eq("fingerprint_pattern", fingerprint)
             .eq("rule", "never")
             .limit(1)
             .execute())
        return bool(r.data)

    # --- voice reply helper (Phase 4 / ADR 003 Discuss verb) ---

    def record_voice_reply(self, *, suggestion_id: int,
                           transcript: str, tenant_slug: str) -> None:
        """Persist a voice transcript onto pilot_suggestions.body_json."""
        self.client.table("pilot_suggestions").update({
            "body_json": {"voice_transcript": transcript},
        }).eq("id", suggestion_id).execute()
