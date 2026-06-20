"""SOP 6.2.5 — 事件产品 → 持有客户 → 客户经理受众解析。"""

from __future__ import annotations

from typing import Any

from core.config_loader import (
    get_advisor_map,
    get_default_advisor_id,
    get_demo_customer,
    get_risk_level_name,
    load_customer_profile,
)
from core.data_store import get_customer_holdings


def resolve_event_audiences(product_code: str) -> list[dict[str, Any]]:
    """
    找出持有指定产品的演示客户及其客户经理。
    同一客户只出现一次；holding_amount 为该产品持仓金额。
    """
    code = (product_code or "").strip()
    if not code:
        return []

    advisor_map = get_advisor_map()
    default_advisor_id = get_default_advisor_id()
    audiences: list[dict[str, Any]] = []

    for customer in load_customer_profile().get("demo_customers") or []:
        cid = customer.get("customer_id")
        if not cid:
            continue
        data = get_customer_holdings(cid)
        if not data:
            continue
        amount = float((data.get("holdings") or {}).get(code) or 0)
        if amount <= 0:
            continue

        advisor_id = customer.get("advisor_id") or default_advisor_id
        advisor = advisor_map.get(advisor_id) or {}
        risk = customer.get("risk_profile") or ""
        audiences.append(
            {
                "customer_id": cid,
                "customer_name": customer.get("name") or cid,
                "risk_profile": risk,
                "risk_profile_name": get_risk_level_name(risk),
                "holding_amount": round(amount, 2),
                "advisor_id": advisor_id,
                "advisor_name": advisor.get("name") or advisor_id,
                "advisor_title": advisor.get("title") or "客户经理",
            }
        )

    return audiences


def get_advisor_record(advisor_id: str) -> dict[str, Any] | None:
    from core.advisor_feishu_cache import enrich_advisor_with_cache

    row = get_advisor_map().get(advisor_id)
    return enrich_advisor_with_cache(row) if row else None


def validate_advisor_feishu_target(advisor: dict[str, Any]) -> str | None:
    from core.advisor_feishu_cache import validate_advisor_feishu_target as _validate

    return _validate(advisor)
