"""产品展示层：活钱类买入统一呈现为活钱存款，不改动底层配仓算法。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.config_loader import get_product_map
from core.models import ProductDelta

DEMAND_DEPOSIT_CODE = "000"
LIQUID_CATEGORY_KEYS = frozenset({"spend", "cash"})


def apply_demand_deposit_display(
    product_deltas: list[ProductDelta],
    holdings: dict[str, float],
) -> list[ProductDelta]:
    """
    活钱类（综合规划 spend / 投资规划 cash）的任何买入，在方案展示上优先归入活钱存款。

    - 客户已持仓 P000：底层 consolidate 会按 rebalance_priority 选 P000，展示层通常无需调整。
    - 客户未持仓 P000：将其他现金类产品的买入合并为 P000 新开仓行（算法层仍按原逻辑计算）。
    """
    pmap = get_product_map()
    deposit = pmap.get(DEMAND_DEPOSIT_CODE)
    if not deposit:
        return product_deltas

    redirect_buy = 0.0
    liquid_cat: str | None = None
    adjusted: list[ProductDelta] = []

    for delta in product_deltas:
        if (
            delta.category in LIQUID_CATEGORY_KEYS
            and delta.product_code != DEMAND_DEPOSIT_CODE
            and delta.action == "buy"
            and delta.delta_amount > 0.01
        ):
            redirect_buy += delta.delta_amount
            liquid_cat = delta.category
            adjusted.append(
                replace(
                    delta,
                    target_amount=delta.current_amount,
                    delta_amount=0.0,
                    action="hold",
                )
            )
        else:
            adjusted.append(delta)

    if redirect_buy < 0.01:
        return product_deltas

    cur = round(holdings.get(DEMAND_DEPOSIT_CODE, 0.0), 2)
    cat_key = liquid_cat or deposit.get("asset_type", "cash")
    p013_idx = next(
        (i for i, d in enumerate(adjusted) if d.product_code == DEMAND_DEPOSIT_CODE),
        None,
    )

    if p013_idx is not None:
        existing = adjusted[p013_idx]
        new_delta = round(existing.delta_amount + redirect_buy, 2)
        new_target = round(existing.target_amount + redirect_buy, 2)
        adjusted[p013_idx] = replace(
            existing,
            target_amount=new_target,
            delta_amount=new_delta,
            action="buy" if new_delta > 0.01 else existing.action,
        )
    else:
        new_target = round(cur + redirect_buy, 2)
        adjusted.append(
            ProductDelta(
                product_code=DEMAND_DEPOSIT_CODE,
                product_name=deposit["name"],
                category=cat_key,
                current_amount=cur,
                target_amount=new_target,
                delta_amount=round(redirect_buy, 2),
                action="buy",
            )
        )
        adjusted.sort(key=lambda d: d.product_code)

    return adjusted


def apply_demand_deposit_to_result(result: Any, holdings: dict[str, float]) -> Any:
    """对 RebalanceResult 应用活钱存款展示规则（原地更新 product_deltas）。"""
    result.product_deltas = apply_demand_deposit_display(
        result.product_deltas, holdings
    )
    return result
