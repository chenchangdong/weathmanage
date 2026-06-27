"""Build compact grounding context for advisor chat."""

from __future__ import annotations

from typing import Any

from core.asset_service import AssetOverviewService, overview_to_dict
from core.config_loader import get_demo_customer, get_risk_level_name


def build_customer_context(customer_id: str) -> dict[str, Any]:
    customer = get_demo_customer(customer_id)
    if not customer:
        return {"customer_id": customer_id, "error": "客户不存在"}
    risk = customer.get("risk_profile", "")
    return {
        "customer_id": customer_id,
        "name": customer.get("name"),
        "age": customer.get("age"),
        "occupation": customer.get("occupation"),
        "risk_profile": risk,
        "risk_profile_name": get_risk_level_name(risk),
        "product_category": customer.get("product_category", "投资规划"),
        "invest_horizon_years": customer.get("invest_horizon_years"),
        "notes": customer.get("notes", ""),
    }


def build_overview_context(customer_id: str, overview: dict[str, Any] | None) -> dict[str, Any]:
    if overview:
        return _compact_overview(overview)
    try:
        svc = AssetOverviewService()
        data = overview_to_dict(svc.build_overview(customer_id))
        return _compact_overview(data)
    except ValueError:
        return {"available": False}


def _compact_overview(data: dict[str, Any]) -> dict[str, Any]:
    mapping = data.get("allocation_mapping") or {}
    categories = []
    for c in data.get("categories") or []:
        categories.append({
            "category": c.get("category"),
            "category_name": c.get("category_name"),
            "current_ratio": c.get("current_ratio"),
            "target_ratio": c.get("target_ratio"),
            "deviation_pct": c.get("deviation_pct"),
            "band": c.get("band"),
            "in_band": c.get("in_band"),
            "current_amount": c.get("current_amount"),
        })
    return {
        "available": True,
        "total_assets": data.get("total_assets"),
        "idle_cash": data.get("idle_cash"),
        "health": data.get("health"),
        "model_code": mapping.get("model_code"),
        "categories": categories,
    }


def build_plan_context(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not plan:
        return {"available": False}
    rb = plan.get("rebalance") or plan
    ex = plan.get("explanation") or {}
    categories = []
    for s in rb.get("category_summary") or []:
        categories.append({
            "category_name": s.get("category_name"),
            "current_ratio": s.get("current_ratio"),
            "final_ratio": s.get("final_ratio"),
            "target_ratio": s.get("target_ratio"),
            "adjust_amount": s.get("adjust_amount"),
            "in_band": s.get("in_band"),
            "band": s.get("band"),
        })
    products = []
    for d in rb.get("product_deltas") or []:
        if (d.get("current_amount") or 0) <= 0 and abs(d.get("delta_amount") or 0) < 1:
            continue
        products.append({
            "product_name": d.get("product_name"),
            "category": d.get("category"),
            "current_amount": d.get("current_amount"),
            "target_amount": d.get("target_amount"),
            "delta_amount": d.get("delta_amount"),
            "action": d.get("action"),
            "limit_hit": d.get("limit_hit"),
        })
    return {
        "available": True,
        "mode": rb.get("mode"),
        "total_assets": rb.get("total_assets"),
        "idle_cash": rb.get("idle_cash"),
        "validation_notes": rb.get("validation_notes"),
        "categories": categories,
        "products": products[:20],
        "rule_explanation": {
            "allocation_logic": ex.get("allocation_logic"),
            "over_under_reason": ex.get("over_under_reason"),
        } if ex else None,
    }


def build_diagnosis_context(diagnosis: dict[str, Any] | None) -> dict[str, Any]:
    if not diagnosis:
        return {"available": False}
    four_money = []
    for x in diagnosis.get("four_money") or []:
        four_money.append({
            "category_name": x.get("category_name"),
            "current_ratio": x.get("current_ratio"),
            "target_ratio": x.get("target_ratio"),
            "band": x.get("band"),
            "in_band": x.get("in_band"),
        })
    flags = []
    for f in diagnosis.get("flags") or []:
        flags.append({
            "label": f.get("label"),
            "severity": f.get("severity"),
            "hint": f.get("hint"),
        })
    perf = diagnosis.get("performance") or {}
    model = diagnosis.get("model_benchmark") or {}
    return {
        "available": True,
        "diagnosis_date": diagnosis.get("diagnosis_date"),
        "composite_score": diagnosis.get("composite_score"),
        "beat_investors_pct": diagnosis.get("beat_investors_pct"),
        "loss_threshold_pct": diagnosis.get("loss_threshold_pct"),
        "performance": {
            "annual_return_pct": perf.get("annual_return_pct"),
            "month_return_pct": perf.get("month_return_pct"),
            "principal_loss_pct": perf.get("principal_loss_pct"),
            "volatility_pct": perf.get("volatility_pct"),
        },
        "model_benchmark": {
            "model_code": model.get("model_code"),
            "expect_annual_return_pct": model.get("expect_annual_return_pct"),
            "expect_volatility_pct": model.get("expect_volatility_pct"),
        },
        "four_money": four_money,
        "flags": flags,
        "score_context": diagnosis.get("score_context"),
        "dimensions": diagnosis.get("dimensions"),
        "conclusions": diagnosis.get("conclusions"),
    }


def build_sop_context(sop: dict[str, Any] | None) -> dict[str, Any]:
    if not sop or not sop.get("ok"):
        return {"available": False}
    events = sop.get("events") or []
    return {
        "available": True,
        "data_date": sop.get("data_date"),
        "event_count": len(events),
        "pending_count": sop.get("pending_count", 0),
        "events": [
            {
                "event_id": e.get("event_id"),
                "product_name": e.get("product_name"),
                "scenario": e.get("scenario"),
                "agent_status": e.get("agent_status"),
                "has_output": e.get("has_output"),
            }
            for e in events[:8]
        ],
    }


from agent_core.journey_state import build_journey_context


def build_journey_context_for_chat(
    customer_id: str,
    *,
    journey: dict[str, Any] | None = None,
    page: str | None = None,
    diagnosis: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_journey_context(
        customer_id,
        journey=journey,
        page=page,
        diagnosis=diagnosis,
        plan=plan,
    )


def build_chat_grounding(
    customer_id: str,
    overview: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
    journey: dict[str, Any] | None = None,
    page: str | None = None,
    sop: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "customer": build_customer_context(customer_id),
        "asset_overview": build_overview_context(customer_id, overview),
        "allocation_plan": build_plan_context(plan),
        "asset_diagnosis": build_diagnosis_context(diagnosis),
        "sop_post_investment": build_sop_context(sop),
        "journey": build_journey_context(
            customer_id,
            journey=journey,
            page=page,
            diagnosis=diagnosis,
            plan=plan,
        ),
    }
