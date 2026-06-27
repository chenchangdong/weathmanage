"""顾问 Agent 可调用工具 — 诊断 / 模式推荐 / 配仓 / 投后 SOP。"""

from __future__ import annotations

from typing import Any

from agent_core.explain_agent import ExplainAgent
from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine
from core.config_loader import get_demo_customer, get_risk_level_name
from core.data_store import get_customer_holdings
from core.sop_agent_service import SopAgentService
from core.sop_event_store import SopEventStore
from core.sop_wealth_flags import _latest_data_date, _latest_events_by_product_composite, _enabled_composite_codes
from core.wealth_journey_service import (
    WealthJourneyService,
    effective_personalized_flags,
    personalized_allocation_block_message,
)

from agent_core.chat_context import build_diagnosis_context, build_plan_context


def _customer_held_products(customer_id: str) -> set[str]:
    data = get_customer_holdings(customer_id)
    if not data:
        return set()
    return {code for code, amt in data["holdings"].items() if float(amt or 0) > 0}


def tool_list_sop_events(customer_id: str) -> dict[str, Any]:
    """列出与客户持仓相关的最新批次 SOP 组合事件。"""
    held = _customer_held_products(customer_id)
    store = SopEventStore()
    all_events = store.list_composite_events()
    latest_date = _latest_data_date(all_events)
    if not latest_date or not held:
        return {
            "ok": True,
            "tool": "list_sop_events",
            "data_date": latest_date,
            "events": [],
            "pending_count": 0,
            "total_in_store": len(all_events),
        }

    enabled = _enabled_composite_codes()
    day_events = [e for e in all_events if e.get("data_date") == latest_date]
    latest = _latest_events_by_product_composite(day_events)

    matched: list[dict[str, Any]] = []
    for (product_code, composite_code), evt in latest.items():
        if composite_code not in enabled or product_code not in held:
            continue
        eid = evt.get("event_id")
        output = store.get_agent_output(eid) if eid else None
        matched.append({
            "event_id": eid,
            "product_code": product_code,
            "product_name": evt.get("product_name"),
            "composite_code": composite_code,
            "scenario": evt.get("scenario"),
            "data_date": evt.get("data_date"),
            "drawdown_detail": evt.get("drawdown_detail"),
            "agent_status": evt.get("agent_status") or ("done" if output else "pending"),
            "has_output": bool(output),
            "client_script_preview": (output or {}).get("client_script", "")[:120] if output else "",
        })

    matched.sort(key=lambda e: e.get("product_name") or "")
    pending = sum(1 for e in matched if e.get("agent_status") in (None, "pending"))

    return {
        "ok": True,
        "tool": "list_sop_events",
        "data_date": latest_date,
        "events": matched,
        "pending_count": pending,
        "total_in_store": len(all_events),
    }


def tool_generate_sop_content(
    *,
    event_id: str | None = None,
    batch: bool = False,
    limit: int = 20,
    use_llm: bool = False,
) -> dict[str, Any]:
    svc = SopAgentService()
    if batch:
        data = svc.run_batch_for_events(None, limit=max(1, min(limit, 100)), use_llm=use_llm)
        return {
            "ok": True,
            "tool": "generate_sop_content",
            "batch": True,
            "processed": data.get("processed"),
            "failed": data.get("failed"),
            "remaining_pending": data.get("remaining_pending"),
            "outputs": data.get("outputs") or [],
            "errors": data.get("errors") or [],
        }
    if not event_id:
        return {"ok": False, "tool": "generate_sop_content", "error": "缺少 event_id"}
    try:
        output = svc.run_for_event(event_id, use_llm=use_llm)
    except ValueError as exc:
        return {"ok": False, "tool": "generate_sop_content", "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "tool": "generate_sop_content", "error": str(exc)}

    return {
        "ok": True,
        "tool": "generate_sop_content",
        "event_id": event_id,
        "output": {
            "event_id": output.get("event_id"),
            "source": output.get("source"),
            "event_description": output.get("event_description"),
            "client_script": output.get("client_script"),
        },
    }


def tool_get_diagnosis(customer_id: str) -> dict[str, Any]:
    svc = WealthJourneyService()
    diagnosis = svc.build_diagnosis(customer_id)
    compact = build_diagnosis_context(diagnosis)
    flags = [
        {"code": f.get("code"), "label": f.get("label"), "severity": f.get("severity")}
        for f in diagnosis.get("flags") or []
    ]
    return {
        "ok": True,
        "tool": "get_diagnosis",
        "diagnosis": diagnosis,
        "summary": {
            "composite_score": diagnosis.get("composite_score"),
            "flag_count": len(flags),
            "flags": flags,
            "health_level": (diagnosis.get("score_context") or {}).get("health_level"),
            "conclusions": diagnosis.get("conclusions") or [],
        },
        "compact": compact,
    }


def tool_recommend_mode(customer_id: str) -> dict[str, Any]:
    svc = WealthJourneyService()
    diagnosis = svc.build_diagnosis(customer_id)
    flags = diagnosis.get("flags") or []
    eff = effective_personalized_flags(flags)
    block = personalized_allocation_block_message(flags)

    if block:
        mode = "smart_one_click"
        mode_label = "全账户一键智能最优配置"
        reason = block
    elif eff:
        mode = "flag_personalized"
        mode_label = "个性化智能配仓"
        labels = "、".join(f.get("label") or f.get("code") or "" for f in eff)
        reason = f"检测到财富健康标志（{labels}），建议按标志驱动调仓。"
    else:
        mode = "optimal_personalized"
        mode_label = "个性化智能配仓（新）"
        reason = "客户配置健康，建议全账户最优大类 + 分步落实。"

    return {
        "ok": True,
        "tool": "recommend_mode",
        "mode": mode,
        "mode_label": mode_label,
        "reason": reason,
        "flag_codes": [f.get("code") for f in eff],
        "can_flag_personalized": block is None and bool(eff),
    }


def tool_run_rebalance(
    customer_id: str,
    *,
    mode: str | None = None,
    product_category: str | None = None,
    idle_cash: float = 0.0,
) -> dict[str, Any]:
    customer = get_demo_customer(customer_id)
    if not customer:
        return {"ok": False, "tool": "run_rebalance", "error": f"客户不存在: {customer_id}"}

    data = get_customer_holdings(customer_id)
    if not data:
        return {"ok": False, "tool": "run_rebalance", "error": f"无持仓: {customer_id}"}

    if not mode:
        rec = tool_recommend_mode(customer_id)
        mode = rec["mode"]

    category = product_category or customer.get("product_category", "投资规划")
    flag_codes: list[str] | None = None

    if mode == "flag_personalized":
        if category != "投资规划":
            return {"ok": False, "tool": "run_rebalance", "error": "个性化配仓仅支持投资规划"}
        diagnosis = WealthJourneyService().build_diagnosis(customer_id)
        flag_codes = [f["code"] for f in effective_personalized_flags(diagnosis.get("flags", []))]
        block = personalized_allocation_block_message(diagnosis.get("flags", []))
        if block:
            return {"ok": False, "tool": "run_rebalance", "error": block, "suggested_mode": "smart_one_click"}

    engine = AutoRebalanceEngine()
    try:
        result = engine.rebalance(
            customer_id=customer_id,
            holdings=data["holdings"],
            idle_cash=idle_cash,
            risk_profile=customer["risk_profile"],
            mode=mode,
            product_category=category,
            flag_codes=flag_codes,
        )
    except ValueError as exc:
        return {"ok": False, "tool": "run_rebalance", "error": str(exc)}

    explain = ExplainAgent().generate(result)
    plan_payload = {
        "rebalance": {
            "customer_id": result.customer_id,
            "mode": result.mode,
            "total_assets": result.total_assets,
            "category_summary": result.category_summary,
            "product_deltas": [
                {
                    "product_code": d.product_code,
                    "product_name": d.product_name,
                    "delta_amount": d.delta_amount,
                    "action": d.action,
                }
                for d in result.product_deltas
                if abs(d.delta_amount) >= 1
            ][:12],
            "validation_notes": result.validation_notes,
        },
        "explanation": explain,
    }
    compact = build_plan_context(plan_payload)

    adj = sum(abs(s.get("adjust_amount") or 0) for s in result.category_summary)
    return {
        "ok": True,
        "tool": "run_rebalance",
        "mode": mode,
        "mode_label": {
            "smart_one_click": "全账户一键智能最优配置",
            "flag_personalized": "个性化智能配仓",
            "optimal_personalized": "个性化智能配仓（新）",
        }.get(mode, mode),
        "plan": plan_payload,
        "compact": compact,
        "summary": {
            "total_assets": result.total_assets,
            "adjust_total": round(adj, 2),
            "validation_notes": result.validation_notes[:3],
            "customer_name": customer.get("name"),
            "risk_profile_name": get_risk_level_name(customer["risk_profile"]),
        },
    }


def execute_tool(name: str, customer_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    if name == "get_diagnosis":
        return tool_get_diagnosis(customer_id)
    if name == "recommend_mode":
        return tool_recommend_mode(customer_id)
    if name == "run_rebalance":
        return tool_run_rebalance(
            customer_id,
            mode=params.get("mode"),
            product_category=params.get("product_category"),
            idle_cash=float(params.get("idle_cash") or 0),
        )
    if name == "list_sop_events":
        return tool_list_sop_events(customer_id)
    if name == "generate_sop_content":
        return tool_generate_sop_content(
            event_id=params.get("event_id"),
            batch=bool(params.get("batch")),
            limit=int(params.get("limit") or 20),
            use_llm=bool(params.get("use_llm")),
        )
    return {"ok": False, "tool": name, "error": f"未知工具: {name}"}
