"""Asset overview service — builds customer home page data."""

from __future__ import annotations

from typing import Any, Optional

from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine, compute_health_level
from core.allocation_config_service import AllocationConfigService
from core.config_loader import (
    INVESTMENT_CARD_KEYS,
    get_allocation_view_mode,
    get_asset_type_aliases,
    get_category_names,
    get_demo_customer,
    get_display_category_names,
    get_product_map,
    get_risk_level_name,
    get_view_profile,
    load_four_money_page,
    load_page_constraint,
)
from core.data_store import get_customer_holdings
from core.models import AssetOverview, CategorySnapshot


class AssetOverviewService:
    def __init__(self) -> None:
        self.engine = AutoRebalanceEngine()
        self.page_config = load_four_money_page()

    def build_overview(
        self,
        customer_id: str,
        role: str = "advisor",
        product_category: Optional[str] = None,
        loss_key: Optional[str] = None,
    ) -> AssetOverview:
        customer = get_demo_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer not found: {customer_id}")

        data = get_customer_holdings(customer_id)
        if not data:
            raise ValueError(f"No holdings for customer: {customer_id}")

        holdings = data["holdings"]
        idle_cash = 0.0
        risk_profile = customer["risk_profile"]
        product_category = product_category or customer.get("product_category", "投资规划")
        view_mode = get_allocation_view_mode(product_category)
        if view_mode == "asset_type":
            return self._build_investment_overview(
                customer=customer,
                customer_id=customer_id,
                holdings=holdings,
                idle_cash=idle_cash,
                risk_profile=risk_profile,
                product_category=product_category,
                role=role,
                loss_key=loss_key,
            )

        total = sum(holdings.values()) + idle_cash

        config_svc = AllocationConfigService()
        resolved = config_svc.resolve_profile_targets(
            product_category, risk_profile, loss_key
        )
        profile_targets = resolved["targets"]
        allocation_mapping = resolved["model"]
        current_cat = self.engine._aggregate_by_category(holdings)
        names = get_category_names()
        product_map = get_product_map()

        categories: list[CategorySnapshot] = []
        all_in_band = True

        for cat in self.engine.categories:
            cfg = profile_targets[cat]
            cur = current_cat.get(cat, 0.0)
            target_ratio = cfg["target"]
            current_ratio = cur / total if total else 0
            deviation = abs(current_ratio - target_ratio)
            target_amount = target_ratio * total
            band = cfg["band"]
            in_band = band[0] <= current_ratio <= band[1]
            if not in_band:
                all_in_band = False

            # 底层产品汇总（仅展示当前有持仓的产品）
            prods = []
            for code, amt in holdings.items():
                if amt <= 0.01:
                    continue
                p = product_map.get(code)
                if p and p.get("category") == cat:
                    prods.append({
                        "code": code,
                        "name": p["name"],
                        "amount": amt,
                        "asset_type": p.get("asset_type"),
                        "asset_type_name": p.get("asset_type_name"),
                    })

            card_cfg = self.page_config.get("category_cards", {}).get(cat, {})
            health_level, _, _ = compute_health_level(in_band)

            categories.append(
                CategorySnapshot(
                    category=cat,
                    category_name=names.get(cat, cat),
                    current_amount=round(cur, 2),
                    current_ratio=round(current_ratio, 4),
                    target_amount=round(target_amount, 2),
                    target_ratio=target_ratio,
                    deviation=round(deviation, 4),
                    deviation_pct=f"{deviation:.1%}",
                    band=band,
                    in_band=in_band,
                    health_level=health_level,
                    products=prods,
                )
            )

        health_level, health_label, health_color = compute_health_level(all_in_band)
        permissions = self._get_permissions(role)

        return AssetOverview(
            customer_id=customer_id,
            customer_name=customer["name"],
            risk_profile=risk_profile,
            risk_profile_name=get_risk_level_name(risk_profile),
            total_assets=round(total, 2),
            idle_cash=round(idle_cash, 2),
            health_level=health_level,
            health_label=health_label,
            health_color=health_color,
            categories=categories,
            page_config={
                "title": self.page_config["page"]["title"],
                "category_cards": self.page_config.get("category_cards", {}),
                "global_actions": self.page_config.get("global_actions", []),
            },
            permissions=permissions,
            product_category=product_category,
            view_mode=view_mode,
            allocation_mapping=allocation_mapping,
        )

    def _build_investment_overview(
        self,
        *,
        customer: dict,
        customer_id: str,
        holdings: dict[str, float],
        idle_cash: float,
        risk_profile: str,
        product_category: str,
        role: str,
        loss_key: Optional[str] = None,
    ) -> AssetOverview:
        """投资规划：按资产类型四卡展示，保障类不计入总资产。"""
        product_map = get_product_map()
        excluded = 0.0
        invest_holdings: dict[str, float] = {}
        for code, amount in holdings.items():
            prod = product_map.get(code)
            if prod and prod.get("asset_type") == "insurance":
                excluded += amount
                continue
            invest_holdings[code] = amount

        total = sum(invest_holdings.values()) + idle_cash
        config_svc = AllocationConfigService()
        resolved = config_svc.resolve_asset_type_targets(
            product_category, risk_profile, loss_key
        )
        profile_targets = resolved["targets"]
        allocation_mapping = resolved["model"]
        names = get_asset_type_aliases()
        current_by_type = {k: 0.0 for k in INVESTMENT_CARD_KEYS}
        for code, amount in invest_holdings.items():
            prod = product_map.get(code)
            if prod and prod.get("asset_type") in current_by_type:
                current_by_type[prod["asset_type"]] += amount

        categories: list[CategorySnapshot] = []
        all_in_band = True
        for cat in INVESTMENT_CARD_KEYS:
            cfg = profile_targets[cat]
            cur = current_by_type.get(cat, 0.0)
            target_ratio = cfg["target"]
            current_ratio = cur / total if total else 0
            deviation = abs(current_ratio - target_ratio)
            target_amount = target_ratio * total
            band = cfg["band"]
            in_band = band[0] <= current_ratio <= band[1]
            if not in_band:
                all_in_band = False

            prods = []
            for code, amt in invest_holdings.items():
                if amt <= 0.01:
                    continue
                p = product_map.get(code)
                if p and p.get("asset_type") == cat:
                    prods.append({
                        "code": code,
                        "name": p["name"],
                        "amount": amt,
                        "asset_type": p.get("asset_type"),
                        "asset_type_name": p.get("asset_type_name"),
                    })

            health_level, _, _ = compute_health_level(in_band)
            categories.append(
                CategorySnapshot(
                    category=cat,
                    category_name=names.get(cat, cat),
                    current_amount=round(cur, 2),
                    current_ratio=round(current_ratio, 4),
                    target_amount=round(target_amount, 2),
                    target_ratio=target_ratio,
                    deviation=round(deviation, 4),
                    deviation_pct=f"{deviation:.1%}",
                    band=band,
                    in_band=in_band,
                    health_level=health_level,
                    products=prods,
                )
            )

        health_level, health_label, health_color = compute_health_level(all_in_band)
        permissions = self._get_permissions(role)
        return AssetOverview(
            customer_id=customer_id,
            customer_name=customer["name"],
            risk_profile=risk_profile,
            risk_profile_name=get_risk_level_name(risk_profile),
            total_assets=round(total, 2),
            idle_cash=round(idle_cash, 2),
            health_level=health_level,
            health_label=health_label,
            health_color=health_color,
            categories=categories,
            page_config={
                "title": self.page_config["page"]["title"],
                "category_cards": self.page_config.get("category_cards", {}),
                "global_actions": self.page_config.get("global_actions", []),
                "view_profile": get_view_profile(product_category),
            },
            permissions=permissions,
            product_category=product_category,
            view_mode="asset_type",
            allocation_mapping=allocation_mapping,
            excluded_insurance_amount=round(excluded, 2),
        )

    def _get_permissions(self, role: str) -> dict[str, bool]:
        perms = load_page_constraint().get("permissions", {}).get(role, {})
        return {
            "can_full_optimize": perms.get("can_full_optimize", False),
            "can_single_optimize": perms.get("can_single_optimize", False),
            "can_manual_tweak": perms.get("can_manual_tweak", False),
            "can_generate_explanation": perms.get("can_generate_explanation", False),
        }


def overview_to_dict(overview: AssetOverview) -> dict[str, Any]:
    data = {
        "customer_id": overview.customer_id,
        "customer_name": overview.customer_name,
        "risk_profile": overview.risk_profile,
        "risk_profile_name": overview.risk_profile_name,
        "total_assets": overview.total_assets,
        "idle_cash": overview.idle_cash,
        "health": {
            "level": overview.health_level,
            "label": overview.health_label,
            "color": overview.health_color,
        },
        "categories": [
            {
                "category": c.category,
                "category_name": c.category_name,
                "current_amount": c.current_amount,
                "current_ratio": c.current_ratio,
                "target_amount": c.target_amount,
                "target_ratio": c.target_ratio,
                "deviation": c.deviation,
                "deviation_pct": c.deviation_pct,
                "band": c.band,
                "in_band": c.in_band,
                "health_level": c.health_level,
                "products": c.products,
                "product_summary": {
                    "count": len(c.products),
                    "total": c.current_amount,
                },
            }
            for c in overview.categories
        ],
        "page_config": overview.page_config,
        "permissions": overview.permissions,
        "product_category": overview.product_category,
        "view_mode": overview.view_mode,
        "allocation_mapping": overview.allocation_mapping,
        "excluded_insurance_amount": overview.excluded_insurance_amount,
    }
    return data
