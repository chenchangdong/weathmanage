"""顾问上下文预加载 — 跨页 bundle。"""

from __future__ import annotations

from typing import Any

from agent_core.advisor_tools import tool_get_diagnosis, tool_list_sop_events
from agent_core.chat_context import (
    build_diagnosis_context,
    build_overview_context,
    build_plan_context,
    build_sop_context,
)
from agent_core.journey_state import build_journey_context
from core.asset_service import AssetOverviewService, overview_to_dict
from core.config_loader import get_demo_customer
from core.sop_batch_scheduler import get_scheduler_status
from core.wealth_journey_service import WealthJourneyService


def build_context_bundle(
    customer_id: str,
    *,
    page: str | None = None,
    journey: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    customer = get_demo_customer(customer_id)
    if not customer:
        raise ValueError(f"客户不存在: {customer_id}")

    diagnosis_raw = None
    try:
        diagnosis_raw = tool_get_diagnosis(customer_id).get("diagnosis")
    except ValueError:
        pass

    overview_raw = None
    try:
        overview_raw = overview_to_dict(
            AssetOverviewService().build_overview(customer_id)
        )
    except ValueError:
        pass

    sop_result = tool_list_sop_events(customer_id)

    journey_ctx = build_journey_context(
        customer_id,
        journey=journey,
        page=page,
        diagnosis=diagnosis_raw,
        plan=plan,
    )

    schedule = get_scheduler_status()

    return {
        "customer_id": customer_id,
        "page": page,
        "diagnosis": diagnosis_raw,
        "diagnosis_compact": build_diagnosis_context(diagnosis_raw),
        "overview": overview_raw,
        "overview_compact": build_overview_context(customer_id, overview_raw),
        "plan_compact": build_plan_context(plan),
        "sop": sop_result,
        "sop_compact": build_sop_context(sop_result),
        "journey": journey_ctx,
        "schedule": {
            "enabled": schedule.get("enabled"),
            "cron_label": schedule.get("cron_label"),
            "next_run_hint": schedule.get("next_run_hint"),
            "run_agent_after_batch": schedule.get("run_agent_after_batch"),
            "push_feishu_after_agent": schedule.get("push_feishu_after_agent"),
        },
    }


def build_inventory_highlight() -> dict[str, Any] | None:
    """财富盘点页：推荐优先关注的客户。"""
    rows = WealthJourneyService().build_inventory()
    if not rows:
        return None
    need = [r for r in rows if (r.get("flag_count") or 0) > 0]
    top = need[0] if need else rows[0]
    return {
        "customer_id": top.get("customer_id"),
        "name": top.get("name"),
        "flag_count": top.get("flag_count"),
        "flags": [
            {"label": f.get("label"), "severity": f.get("severity")}
            for f in (top.get("flags") or [])[:3]
        ],
        "need_care_count": len(need),
        "total_count": len(rows),
    }
