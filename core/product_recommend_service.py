"""AI 产品推荐（模拟）— 按产品 risk_level 与客户风险档位匹配。"""

from __future__ import annotations

from typing import Any

from core.config_loader import (
    get_demo_customer,
    get_products_for_display_category,
    get_risk_level_name,
)
from core.data_store import get_customer_holdings


# 客户 risk_profile → 数值档位 1~5（与 product risk_level 对齐）
CUSTOMER_RISK_LEVEL_NUMERIC: dict[str, int] = {
    "conservative": 1,
    "prudent": 2,
    "balanced": 3,
    "growth": 4,
    "aggressive": 5,
}


def customer_risk_level_numeric(risk_profile: str) -> int:
    return CUSTOMER_RISK_LEVEL_NUMERIC.get(risk_profile, 3)


class ProductRecommendService:
    def recommend(
        self,
        customer_id: str,
        category: str,
        exclude_codes: list[str] | None = None,
        max_count: int = 2,
    ) -> dict[str, Any]:
        customer = get_demo_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer not found: {customer_id}")

        products_raw, names = get_products_for_display_category(category)
        if category not in names and not products_raw:
            raise ValueError(f"Unknown category: {category}")

        holdings_data = get_customer_holdings(customer_id) or {}
        holdings = holdings_data.get("holdings") or {}
        held_codes = {
            code for code, amount in holdings.items() if (amount or 0) > 0.01
        }
        blocked = held_codes | set(exclude_codes or [])

        risk_profile = customer.get("risk_profile", "balanced")
        customer_level = customer_risk_level_numeric(risk_profile)
        customer_level_name = get_risk_level_name(risk_profile)

        pool: list[dict[str, Any]] = []
        for p in products_raw:
            code = p["code"]
            if code in blocked:
                continue
            prod_level = int(p.get("risk_level") or 0)
            if prod_level <= 0:
                continue
            distance = abs(prod_level - customer_level)
            pool.append({
                "code": code,
                "name": p["name"],
                "category": category,
                "category_name": names.get(category, category),
                "asset_type": p.get("asset_type"),
                "asset_type_name": p.get("asset_type_name"),
                "min_amount": p.get("min_amount", 0),
                "max_amount": p.get("max_amount"),
                "rebalance_priority": p.get("rebalance_priority", 3),
                "risk_level": prod_level,
                "risk_distance": distance,
                "recommend_reason": (
                    f"产品风险等级 R{prod_level} 与客户风险档位"
                    f"（{customer_level_name}·档位{customer_level}）最接近"
                ),
            })

        pool.sort(
            key=lambda item: (
                item["risk_distance"],
                item.get("rebalance_priority", 3),
                item["code"],
            )
        )
        recommended = pool[: max(0, max_count)]

        return {
            "category": category,
            "category_name": names.get(category, category),
            "customer_id": customer_id,
            "customer_name": customer.get("name"),
            "customer_risk_profile": risk_profile,
            "customer_risk_level": customer_level,
            "customer_risk_level_name": customer_level_name,
            "source": "mock_risk_match",
            "products": recommended,
        }
