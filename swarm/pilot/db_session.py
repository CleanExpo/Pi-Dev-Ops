"""DB session middleware — sets `app.current_tenant_slug` per ADR 002.

The RLS policy on every pilot_* table reads current_setting('app.current_tenant_slug', true).
Every connection touching pilot_* tables must go through with_tenant_context
OR use Memory (which sets the session var in __init__). Forgetting the setting
causes queries to return zero rows — correct + safe + loud.
"""
import os
from contextlib import contextmanager


def current_tenant_slug() -> str:
    return os.environ.get("PILOT_TENANT_SLUG", "phill")


@contextmanager
def with_tenant_context(client, tenant_slug: str):
    client.rpc("set_config", {
        "setting_name": "app.current_tenant_slug",
        "new_value": tenant_slug,
        "is_local": True,
    }).execute()
    try:
        yield client
    finally:
        try:
            client.rpc("set_config", {
                "setting_name": "app.current_tenant_slug",
                "new_value": "",
                "is_local": True,
            }).execute()
        except Exception:
            pass
