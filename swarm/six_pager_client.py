"""First-client and mandatory CCW health sections for the daily six-pager."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .ccw_support_contract import SupportSnapshot, SupportState

RowsLoader = Callable[[str], list[dict]]


def render_ccw_client_health(snapshot: SupportSnapshot) -> str:
    identity = snapshot.latest_run_id or "missing-run"
    if snapshot.state is SupportState.QUIET_HEALTHY:
        status = "certified quiet from fresh source and consumer evidence"
    else:
        status = "FAIL-CLOSED — action required; healthy suppression prohibited"
    return (
        "🚨 CCW CLIENT HEALTH — " + snapshot.state.value + "\n"
        f"Reason: {snapshot.reason_code} · source run: {identity}\n"
        f"{status} · pending {snapshot.pending_count} · "
        f"over-30m {snapshot.open_over_30m_count} · "
        f"escalations {snapshot.unresolved_escalation_count}"
    )


def render_first_client_section(repo_root: Path, load_rows: RowsLoader) -> str | None:
    try:
        from . import client_priority
    except Exception:  # noqa: BLE001
        return None
    first_clients = client_priority.list_first_clients()
    if not first_clients:
        return None
    ledgers = {
        "cfo": ".harness/swarm/cfo_state.jsonl",
        "cmo": ".harness/swarm/cmo_state.jsonl",
        "cto": ".harness/swarm/cto_state.jsonl",
        "cs": ".harness/swarm/cs_state.jsonl",
    }
    data = {
        name: {row.get("business_id"): row for row in load_rows(path)}
        for name, path in ledgers.items()
    }
    blocks: list[str] = []
    for business_id in first_clients:
        rows = {name: values.get(business_id) for name, values in data.items()}
        if not any(rows.values()):
            continue
        block = [f"⭐ FIRST CLIENT — {business_id}"]
        cs_row = rows["cs"]
        if cs_row:
            _append_cs(block, business_id, cs_row, client_priority)
        cfo_row = rows["cfo"]
        if cfo_row and cfo_row.get("mrr") is not None and cfo_row.get("nrr") is not None:
            block.append(f"  CFO: ${cfo_row['mrr']:,.0f} MRR | NRR {cfo_row['nrr']:.0%}")
        cto_row = rows["cto"]
        if cto_row and cto_row.get("dora_band") and cto_row.get("uptime_pct") is not None:
            block.append(
                f"  CTO: DORA {cto_row['dora_band']} | uptime {cto_row['uptime_pct']:.4%}"
            )
        cmo_row = rows["cmo"]
        if cmo_row and cmo_row.get("total_spend_usd") is not None:
            ratio = cmo_row.get("ltv_cac_ratio")
            ratio_text = f"L:C {ratio:.2f}" if ratio is not None else "L:C n/a"
            block.append(
                f"  CMO: ${cmo_row['total_spend_usd']:,.0f} attributed spend | {ratio_text}"
            )
        blocks.append("\n".join(block))
    return "\n\n".join(blocks) if blocks else None


def _append_cs(block: list[str], business_id: str, row: dict, priority: object) -> None:
    response = row.get("avg_first_response_minutes")
    nps, grr = row.get("nps"), row.get("grr_pct")
    threats = row.get("open_enterprise_churn_threats", 0)
    alert = priority.first_client_first_response_alert(business_id)
    critical = priority.first_client_first_response_critical(business_id)
    state = "✅ within SLA"
    if response is not None and response > critical:
        state = f"🔴 SLA BREACH ({response:.0f}m > {critical:.0f}m)"
    elif response is not None and response > alert:
        state = f"🟡 watching ({response:.0f}m > {alert:.0f}m)"
    if None not in (nps, grr, response):
        block.append(
            f"  CS: NPS {nps:.0f} | GRR {grr:.0%} | first-response {response:.0f}m | "
            f"{threats} churn-threats | {state}"
        )
    else:
        block.append("  CS: partial data — see section 4.")
