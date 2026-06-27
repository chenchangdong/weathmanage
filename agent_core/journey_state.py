"""财富旅程状态 — 顾问 Agent 编排用。"""

from __future__ import annotations

from typing import Any

JOURNEY_STEPS: list[dict[str, str]] = [
    {"id": "inventory", "label": "财富盘点", "href": "wealth_inventory.html"},
    {"id": "diagnosis", "label": "资产诊断", "href": "asset_diagnosis.html"},
    {"id": "allocation_setup", "label": "智能资配", "href": "smart_allocation_setup.html"},
    {"id": "allocation_work", "label": "配仓方案", "href": "smart_allocation.html"},
    {"id": "plan_review", "label": "方案落地", "href": "smart_allocation.html"},
    {"id": "post_investment", "label": "投后SOP", "href": "sop_agent.html"},
]

_STEP_INDEX = {s["id"]: i for i, s in enumerate(JOURNEY_STEPS)}


def infer_stage_from_page(page: str | None) -> str:
    name = (page or "").split("/")[-1].lower()
    mapping = {
        "wealth_inventory.html": "inventory",
        "asset_diagnosis.html": "diagnosis",
        "smart_allocation_setup.html": "allocation_setup",
        "smart_allocation.html": "allocation_work",
        "sop_agent.html": "post_investment",
    }
    return mapping.get(name, "inventory")


def infer_stage_from_artifacts(
    *,
    page: str | None = None,
    has_diagnosis: bool = False,
    has_plan: bool = False,
    completed_steps: list[str] | None = None,
) -> str:
    done = set(completed_steps or [])
    if has_plan or "allocation_work" in done:
        return "allocation_work"
    if has_diagnosis or "diagnosis" in done:
        page_stage = infer_stage_from_page(page)
        if page_stage in ("allocation_setup", "allocation_work"):
            return page_stage
        return "diagnosis"
    page_stage = infer_stage_from_page(page)
    return page_stage if page_stage != "inventory" else "inventory"


def recommended_next_stage(stage: str, *, has_plan: bool = False) -> str | None:
    idx = _STEP_INDEX.get(stage, 0)
    if idx + 1 < len(JOURNEY_STEPS):
        return JOURNEY_STEPS[idx + 1]["id"]
    return None


def build_journey_context(
    customer_id: str,
    *,
    journey: dict[str, Any] | None = None,
    page: str | None = None,
    diagnosis: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    j = dict(journey or {})
    completed = list(j.get("completed_steps") or [])
    has_diagnosis = bool(diagnosis and diagnosis.get("composite_score") is not None)
    has_plan = bool(plan and (plan.get("rebalance") or plan.get("mode")))
    stage = j.get("stage") or infer_stage_from_artifacts(
        page=page,
        has_diagnosis=has_diagnosis,
        has_plan=has_plan,
        completed_steps=completed,
    )
    if has_diagnosis and "diagnosis" not in completed:
        completed.append("diagnosis")
    if has_plan and "allocation_work" not in completed:
        completed.append("allocation_work")

    next_id = recommended_next_stage(stage, has_plan=has_plan)
    next_step = next((s for s in JOURNEY_STEPS if s["id"] == next_id), None)

    return {
        "customer_id": customer_id,
        "stage": stage,
        "stage_label": next((s["label"] for s in JOURNEY_STEPS if s["id"] == stage), stage),
        "completed_steps": completed,
        "recommended_next": next_id,
        "recommended_next_label": (next_step or {}).get("label"),
        "recommended_next_href": (next_step or {}).get("href"),
        "steps": JOURNEY_STEPS,
        "has_diagnosis": has_diagnosis,
        "has_plan": has_plan,
    }
