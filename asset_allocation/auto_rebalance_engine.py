"""Auto rebalance engine — config-driven, core calculation logic."""

from __future__ import annotations

from typing import Any

from core.allocation_config_service import AllocationConfigService
from core.config_loader import (
    INVESTMENT_CARD_KEYS,
    get_asset_type_aliases,
    get_category_names,
    get_display_category_names,
    get_product_map,
    get_products_by_asset_type,
    get_products_by_category,
    is_product_limit_validation_enabled,
    load_four_money_page,
    load_four_money_rule,
    load_page_constraint,
)
from core.models import ProductDelta, RebalanceResult


class AutoRebalanceEngine:
    """四笔钱智能配仓引擎：优先存量调仓、最小资金异动、落在模型区间。"""

    def __init__(self) -> None:
        load_four_money_rule.cache_clear()
        self.rule = load_four_money_rule()
        self.products = get_product_map()
        self.by_category = get_products_by_category()
        self.by_asset_type = get_products_by_asset_type()
        self.solver = self.rule.get("solver", {})
        self.categories = list(self.rule.get("categories", {}).keys())
        self.config_svc = AllocationConfigService()

    @staticmethod
    def _product_limits_enabled() -> bool:
        return is_product_limit_validation_enabled()

    @staticmethod
    def _investment_holdings(holdings: dict[str, float], products: dict[str, Any]) -> dict[str, float]:
        filtered: dict[str, float] = {}
        for code, amount in holdings.items():
            prod = products.get(code)
            if prod and prod.get("asset_type") == "insurance":
                continue
            filtered[code] = amount
        return filtered

    def rebalance(
        self,
        customer_id: str,
        holdings: dict[str, float],
        idle_cash: float,
        risk_profile: str,
        mode: str = "smart_one_click",
        locked_categories: list[str] | None = None,
        manual_overrides: dict[str, float] | None = None,
        target_category: str | None = None,
        product_category: str = "投资规划",
    ) -> RebalanceResult:
        """
        一键智能配仓。

        Args:
            customer_id: 客户ID
            holdings: 当前各产品持仓 {product_code: amount}
            idle_cash: 闲置资金
            risk_profile: 风险画像 conservative/balanced/aggressive
            mode: smart_one_click | manual_tweak
            locked_categories: 人工微调时锁定的大类
            manual_overrides: 人工指定的大类目标金额
            target_category: 单类优化时指定的大类
        """
        if product_category == "投资规划":
            return self._rebalance_investment_planning(
                customer_id=customer_id,
                holdings=holdings,
                idle_cash=idle_cash,
                risk_profile=risk_profile,
                mode=mode,
                locked_categories=locked_categories,
                manual_overrides=manual_overrides,
                target_category=target_category,
                product_category=product_category,
            )

        locked = set(locked_categories or [])
        overrides = manual_overrides or {}

        # 配置链路：客户风险 → 组合映射 → 模型 → 四笔钱阈值
        resolved = self.config_svc.resolve_profile_targets(
            product_category, risk_profile
        )
        profile_targets = {"targets": resolved["targets"]}
        self._last_model_code = resolved["model"]["model_code"]

        total = sum(holdings.values()) + idle_cash
        if total <= 0:
            raise ValueError("Total assets must be positive")

        # 计算当前大类金额
        current_cat = self._aggregate_by_category(holdings)

        prefer_existing = self.solver.get("prefer_existing_holdings", True)
        consolidate = self.solver.get("consolidate_category_rebalance", False)
        cat_names = get_category_names()

        if target_category is None:
            target_cat, product_targets, alloc_notes, limit_hits = (
                self._solve_allocate_with_limit_freeze(
                    total=total,
                    current_cat=current_cat,
                    profile_targets=profile_targets["targets"],
                    holdings=holdings,
                    locked=locked,
                    overrides=overrides,
                    categories=self.categories,
                    cat_names=cat_names,
                    aggregate_fn=self._target_cat_from_products,
                    allocate_fn=lambda tc: self._allocate_products(
                        target_cat=tc,
                        current_holdings=holdings,
                        prefer_existing=prefer_existing,
                        consolidate=consolidate,
                        only_category=None,
                    ),
                )
            )
        else:
            target_cat = self._solve_category_targets(
                total=total,
                current_cat=current_cat,
                profile_targets=profile_targets["targets"],
                locked=locked,
                overrides=overrides,
                target_category=target_category,
            )
            product_targets, alloc_notes, limit_hits = self._allocate_products(
                target_cat=target_cat,
                current_holdings=holdings,
                prefer_existing=prefer_existing,
                consolidate=consolidate,
                only_category=target_category,
            )

        # 构建输出：大类展示与校验均以产品目标加总为准（与调仓明细一致）
        product_deltas = self._build_deltas(holdings, product_targets, limit_hits)
        actual_target_cat = self._target_cat_from_products(product_targets)
        category_summary = self._build_category_summary(
            total, current_cat, actual_target_cat, profile_targets["targets"]
        )
        notes = list(alloc_notes)
        if target_category:
            deployed = sum(product_targets.values())
            if abs(deployed - total) > 0.01:
                gap = total - deployed
                cat_name = get_category_names().get(target_category, target_category)
                notes.append(
                    f"单类优化仅调整{cat_name}，其余大类保持现仓；"
                    f"本次方案未纳入配置{gap:,.0f}元（约占总资产{gap / total:.1%}）"
                )
        notes.extend(
            self._validate(
                total, actual_target_cat, profile_targets["targets"], product_deltas
            )
        )

        return RebalanceResult(
            customer_id=customer_id,
            risk_profile=risk_profile,
            total_assets=total,
            idle_cash=idle_cash,
            category_targets=actual_target_cat,
            category_summary=category_summary,
            product_deltas=product_deltas,
            validation_notes=notes,
            mode=mode,
            locked_categories=list(locked),
            view_mode="four_money",
            product_category=product_category,
        )

    def _rebalance_investment_planning(
        self,
        *,
        customer_id: str,
        holdings: dict[str, float],
        idle_cash: float,
        risk_profile: str,
        mode: str,
        locked_categories: list[str] | None,
        manual_overrides: dict[str, float] | None,
        target_category: str | None,
        product_category: str,
    ) -> RebalanceResult:
        """投资规划：按资产类型四卡配仓，保障类不计入总资产且不参与调仓。"""
        locked = set(locked_categories or [])
        overrides = manual_overrides or {}
        resolved = self.config_svc.resolve_asset_type_targets(product_category, risk_profile)
        profile_targets = resolved["targets"]
        self._last_model_code = resolved["model"]["model_code"]
        invest_holdings = self._investment_holdings(holdings, self.products)

        total = sum(invest_holdings.values()) + idle_cash
        if total <= 0:
            raise ValueError("Total assets must be positive")

        current_cat = self._aggregate_by_asset_type(invest_holdings)
        prefer_existing = self.solver.get("prefer_existing_holdings", True)
        consolidate = self.solver.get("consolidate_category_rebalance", False)
        names = get_asset_type_aliases()
        invest_cats = list(INVESTMENT_CARD_KEYS)

        if target_category is None:
            target_cat, product_targets, alloc_notes, limit_hits = (
                self._solve_allocate_with_limit_freeze(
                    total=total,
                    current_cat=current_cat,
                    profile_targets=profile_targets,
                    holdings=invest_holdings,
                    locked=locked,
                    overrides=overrides,
                    categories=invest_cats,
                    cat_names=names,
                    aggregate_fn=self._target_cat_from_asset_type,
                    allocate_fn=lambda tc: self._allocate_products_asset_type(
                        target_cat=tc,
                        current_holdings=invest_holdings,
                        prefer_existing=prefer_existing,
                        consolidate=consolidate,
                        only_category=None,
                    ),
                )
            )
        else:
            target_cat = self._solve_category_targets(
                total=total,
                current_cat=current_cat,
                profile_targets=profile_targets,
                locked=locked,
                overrides=overrides,
                target_category=target_category,
                categories=invest_cats,
            )
            product_targets, alloc_notes, limit_hits = self._allocate_products_asset_type(
                target_cat=target_cat,
                current_holdings=invest_holdings,
                prefer_existing=prefer_existing,
                consolidate=consolidate,
                only_category=target_category,
            )

        product_deltas = self._build_deltas(
            invest_holdings, product_targets, limit_hits, use_asset_type_key=True
        )
        actual_target_cat = self._target_cat_from_asset_type(product_targets)
        category_summary = self._build_category_summary(
            total,
            current_cat,
            actual_target_cat,
            profile_targets,
            categories=list(INVESTMENT_CARD_KEYS),
            names=names,
        )
        notes = list(alloc_notes)
        if target_category and target_category in INVESTMENT_CARD_KEYS:
            deployed = sum(product_targets.values())
            if abs(deployed - total) > 0.01:
                gap = total - deployed
                cat_name = names.get(target_category, target_category)
                notes.append(
                    f"单类优化仅调整{cat_name}，其余资产类型保持现仓；"
                    f"本次方案未纳入配置{gap:,.0f}元（约占总资产{gap / total:.1%}）"
                )
        notes.extend(
            self._validate(
                total,
                actual_target_cat,
                profile_targets,
                product_deltas,
                categories=list(INVESTMENT_CARD_KEYS),
                names=names,
            )
        )

        return RebalanceResult(
            customer_id=customer_id,
            risk_profile=risk_profile,
            total_assets=total,
            idle_cash=idle_cash,
            category_targets=actual_target_cat,
            category_summary=category_summary,
            product_deltas=product_deltas,
            validation_notes=notes,
            mode=mode,
            locked_categories=list(locked),
            view_mode="asset_type",
            product_category=product_category,
        )

    def apply_manual_product_targets(
        self,
        customer_id: str,
        holdings: dict[str, float],
        idle_cash: float,
        risk_profile: str,
        product_targets: dict[str, float],
        baseline_product_targets: dict[str, float] | None = None,
        product_category: str = "投资规划",
    ) -> RebalanceResult:
        """人工二次调整：仅更新指定产品目标，其余产品保持方案基准不变。"""
        if product_category == "投资规划":
            return self._apply_manual_investment(
                customer_id=customer_id,
                holdings=holdings,
                idle_cash=idle_cash,
                risk_profile=risk_profile,
                product_targets=product_targets,
                baseline_product_targets=baseline_product_targets,
                product_category=product_category,
            )

        resolved = self.config_svc.resolve_profile_targets(
            product_category, risk_profile
        )
        profile_targets = resolved["targets"]

        total = sum(holdings.values()) + idle_cash
        if total <= 0:
            raise ValueError("Total assets must be positive")

        if baseline_product_targets is not None:
            clamped = dict(baseline_product_targets)
        else:
            clamped = dict(holdings)
            for code, cur in holdings.items():
                clamped.setdefault(code, cur)

        raw_targets = dict(clamped)
        for code, amount in product_targets.items():
            if self.products.get(code):
                raw_targets[code] = max(0.0, float(amount))

        clamp_notes: list[str] = []
        limit_hits: dict[str, str] = {}
        for code, raw in raw_targets.items():
            prod = self.products.get(code)
            if not prod:
                continue
            cur = holdings.get(code, 0.0)
            clamped[code] = self._clamp_product(code, raw, current=cur)
            side = self._limit_side(code, raw, current=cur)
            if side == "max":
                limit_hits[code] = side
                mx = prod.get("max_amount", raw)
                clamp_notes.append(
                    f"{prod['name']}已达产品金额上限"
                    f"（{prod.get('min_amount', 0):,.0f}~{mx:,.0f}元）"
                )
            elif cur > 0.01 and clamped[code] <= 0.01:
                limit_hits[code] = "liquidate"

        current_cat = self._aggregate_by_category(holdings)
        target_cat = self._target_cat_from_products(clamped)

        product_deltas = self._build_deltas(
            holdings, clamped, limit_hits, include_target_codes=True
        )
        category_summary = self._build_category_summary(
            total, current_cat, target_cat, profile_targets
        )

        notes: list[str] = []
        targets_sum = sum(clamped.values())
        if abs(targets_sum - total) > 0.01:
            notes.append(
                f"产品目标合计{targets_sum:,.0f}元与总资产{total:,.0f}元不一致，"
                f"差额{targets_sum - total:+,.0f}元，请继续调整"
            )
        notes.extend(clamp_notes)
        val_notes = self._validate(
            total, target_cat, profile_targets, product_deltas
        )
        ok_msg = "配置方案已落在模型区间内，校验通过"
        if not (notes and val_notes == [ok_msg]):
            notes.extend(val_notes)

        return RebalanceResult(
            customer_id=customer_id,
            risk_profile=risk_profile,
            total_assets=total,
            idle_cash=idle_cash,
            category_targets=target_cat,
            category_summary=category_summary,
            product_deltas=product_deltas,
            validation_notes=notes,
            mode="manual_product_edit",
            locked_categories=[],
            view_mode="four_money",
            product_category=product_category,
        )

    def _apply_manual_investment(
        self,
        *,
        customer_id: str,
        holdings: dict[str, float],
        idle_cash: float,
        risk_profile: str,
        product_targets: dict[str, float],
        baseline_product_targets: dict[str, float] | None,
        product_category: str,
    ) -> RebalanceResult:
        resolved = self.config_svc.resolve_asset_type_targets(product_category, risk_profile)
        profile_targets = resolved["targets"]
        invest_holdings = self._investment_holdings(holdings, self.products)
        total = sum(invest_holdings.values()) + idle_cash
        if total <= 0:
            raise ValueError("Total assets must be positive")

        if baseline_product_targets is not None:
            clamped = {
                k: v for k, v in baseline_product_targets.items()
                if self.products.get(k, {}).get("asset_type") != "insurance"
            }
        else:
            clamped = dict(invest_holdings)

        raw_targets = dict(clamped)
        for code, amount in product_targets.items():
            prod = self.products.get(code)
            if prod and prod.get("asset_type") != "insurance":
                raw_targets[code] = max(0.0, float(amount))

        clamp_notes: list[str] = []
        limit_hits: dict[str, str] = {}
        for code, raw in raw_targets.items():
            prod = self.products.get(code)
            if not prod or prod.get("asset_type") == "insurance":
                continue
            cur = invest_holdings.get(code, 0.0)
            clamped[code] = self._clamp_product(code, raw, current=cur)
            side = self._limit_side(code, raw, current=cur)
            if side == "max":
                limit_hits[code] = side
                mx = prod.get("max_amount", raw)
                clamp_notes.append(
                    f"{prod['name']}已达产品金额上限"
                    f"（{prod.get('min_amount', 0):,.0f}~{mx:,.0f}元）"
                )
            elif cur > 0.01 and clamped[code] <= 0.01:
                limit_hits[code] = "liquidate"

        current_cat = self._aggregate_by_asset_type(invest_holdings)
        target_cat = self._target_cat_from_asset_type(clamped)
        names = get_asset_type_aliases()
        product_deltas = self._build_deltas(
            invest_holdings, clamped, limit_hits,
            include_target_codes=True, use_asset_type_key=True,
        )
        category_summary = self._build_category_summary(
            total, current_cat, target_cat, profile_targets,
            categories=list(INVESTMENT_CARD_KEYS), names=names,
        )

        notes: list[str] = []
        targets_sum = sum(clamped.values())
        if abs(targets_sum - total) > 0.01:
            notes.append(
                f"产品目标合计{targets_sum:,.0f}元与可配置总资产{total:,.0f}元不一致，"
                f"差额{targets_sum - total:+,.0f}元，请继续调整"
            )
        notes.extend(clamp_notes)
        val_notes = self._validate(
            total, target_cat, profile_targets, product_deltas,
            categories=list(INVESTMENT_CARD_KEYS), names=names,
        )
        ok_msg = "配置方案已落在模型区间内，校验通过"
        if not (notes and val_notes == [ok_msg]):
            notes.extend(val_notes)

        return RebalanceResult(
            customer_id=customer_id,
            risk_profile=risk_profile,
            total_assets=total,
            idle_cash=idle_cash,
            category_targets=target_cat,
            category_summary=category_summary,
            product_deltas=product_deltas,
            validation_notes=notes,
            mode="manual_product_edit",
            locked_categories=[],
            view_mode="asset_type",
            product_category=product_category,
        )

    def _aggregate_by_category(self, holdings: dict[str, float]) -> dict[str, float]:
        result = {c: 0.0 for c in self.categories}
        for code, amount in holdings.items():
            prod = self.products.get(code)
            if prod and prod.get("category"):
                result[prod["category"]] += amount
        return result

    def _aggregate_by_asset_type(self, holdings: dict[str, float]) -> dict[str, float]:
        result = {c: 0.0 for c in INVESTMENT_CARD_KEYS}
        for code, amount in holdings.items():
            prod = self.products.get(code)
            at = prod.get("asset_type") if prod else None
            if at in result:
                result[at] += amount
        return result

    def _target_cat_from_asset_type(self, product_targets: dict[str, float]) -> dict[str, float]:
        result = {c: 0.0 for c in INVESTMENT_CARD_KEYS}
        for code, amount in product_targets.items():
            prod = self.products.get(code)
            at = prod.get("asset_type") if prod else None
            if at in result:
                result[at] += amount
        return {cat: round(amt, 2) for cat, amt in result.items()}

    def _allocate_products_asset_type(
        self,
        target_cat: dict[str, float],
        current_holdings: dict[str, float],
        prefer_existing: bool,
        consolidate: bool = False,
        only_category: str | None = None,
    ) -> tuple[dict[str, float], list[str], dict[str, str]]:
        return self._allocate_products(
            target_cat=target_cat,
            current_holdings=current_holdings,
            prefer_existing=prefer_existing,
            consolidate=consolidate,
            only_category=only_category,
            product_index=self.by_asset_type,
            cat_names=get_asset_type_aliases(),
        )

    def _target_cat_from_products(self, product_targets: dict[str, float]) -> dict[str, float]:
        """将产品目标金额汇总为各大类实际目标（与产品调仓明细一致）。"""
        result = {c: 0.0 for c in self.categories}
        for code, amount in product_targets.items():
            prod = self.products.get(code)
            if prod and prod.get("category"):
                result[prod["category"]] += amount
        return {cat: round(amt, 2) for cat, amt in result.items()}

    def _solve_category_targets(
        self,
        total: float,
        current_cat: dict[str, float],
        profile_targets: dict[str, Any],
        locked: set[str],
        overrides: dict[str, float],
        target_category: str | None,
        categories: list[str] | None = None,
    ) -> dict[str, float]:
        """求解各大类/资产类型目标金额，优先落在模型区间，最小异动。"""
        cats = categories or self.categories
        target: dict[str, float] = {}
        fallback = self.solver.get("fallback_strategy", "band_midpoint")

        # 1. 应用人工覆盖
        for cat in cats:
            if cat in overrides:
                target[cat] = overrides[cat]
            elif cat in locked:
                target[cat] = current_cat[cat]

        # 2. 单类优化：只调整指定类，其余大类冻结在当前持仓（不归一化凑满总资产）
        if target_category and target_category in cats:
            locked_for_single = set(cats) - {target_category}
            for cat in locked_for_single:
                if cat not in target:
                    target[cat] = current_cat[cat]

            cfg = profile_targets[target_category]
            ideal = cfg["target"] * total
            lo, hi = cfg["band"][0] * total, cfg["band"][1] * total
            current = current_cat.get(target_category, 0.0)

            if self.solver.get("minimize_cash_movement", True):
                if lo <= current <= hi:
                    resolved = current
                elif current > hi:
                    # 单类优化超配：减至模型基准值（裁剪至区间内）
                    resolved = self._resolve_fallback_target("benchmark", ideal, lo, hi)
                else:
                    # 单类优化低配：沿用 fallback_strategy
                    resolved = self._resolve_fallback_target(fallback, ideal, lo, hi)
            else:
                resolved = self._clamp(ideal, lo, hi)

            # 其余大类不动时，本类增配上限 = 总资产 − 其他大类当前持仓
            other_sum = sum(
                current_cat.get(c, 0.0)
                for c in cats
                if c != target_category
            )
            max_for_cat = total - other_sum
            target[target_category] = min(resolved, max_for_cat)
            return target

        # 3. 全账户优化
        unlocked = [c for c in cats if c not in target]
        if not unlocked:
            return self._normalize_targets(
                target, total, profile_targets, locked | set(overrides.keys()), categories=cats
            )

        allocated = sum(target.values())
        remaining = total - allocated

        for cat in unlocked:
            cfg = profile_targets[cat]
            ideal = cfg["target"] * total
            lo, hi = cfg["band"][0] * total, cfg["band"][1] * total

            if self.solver.get("minimize_cash_movement", True):
                # 最小异动：从当前值向理想值移动，但不超出区间
                current = current_cat[cat]
                if lo <= current <= hi:
                    target[cat] = current  # 已在区间内，不动
                else:
                    target[cat] = self._resolve_fallback_target(fallback, ideal, lo, hi)
            else:
                target[cat] = self._clamp(ideal, lo, hi)

        return self._normalize_targets(
            target, total, profile_targets, locked | set(overrides.keys()), categories=cats
        )

    def _normalize_targets(
        self,
        target: dict[str, float],
        total: float,
        profile_targets: dict[str, Any],
        frozen: set[str],
        categories: list[str] | None = None,
    ) -> dict[str, float]:
        """确保目标金额之和等于总资产，冻结类不动。"""
        cats = categories or self.categories
        current_sum = sum(target.values())
        if abs(current_sum - total) < 0.01:
            return target

        adjustable = [c for c in cats if c not in frozen]
        if not adjustable:
            return target

        diff = total - current_sum
        per = diff / len(adjustable)
        for cat in adjustable:
            lo = profile_targets[cat]["band"][0] * total
            hi = profile_targets[cat]["band"][1] * total
            target[cat] = self._clamp(target[cat] + per, lo, hi)

        # 二次归一化
        current_sum = sum(target.values())
        if abs(current_sum - total) > 0.01 and adjustable:
            last = adjustable[-1]
            target[last] += total - current_sum

        return target

    def _freeze_priority(self, categories: list[str]) -> list[str]:
        """触顶冻结重算时的大类/资产类型优先顺序（越靠前越先冻结）。"""
        if set(categories) == set(INVESTMENT_CARD_KEYS):
            preferred = list(INVESTMENT_CARD_KEYS)
        else:
            preferred = ["protect", "spend", "preserve", "grow"]
        ordered = [c for c in preferred if c in categories]
        ordered.extend(c for c in categories if c not in ordered)
        return ordered

    def _solve_allocate_with_limit_freeze(
        self,
        *,
        total: float,
        current_cat: dict[str, float],
        profile_targets: dict[str, Any],
        holdings: dict[str, float],
        locked: set[str],
        overrides: dict[str, float],
        categories: list[str],
        cat_names: dict[str, str],
        aggregate_fn,
        allocate_fn,
    ) -> tuple[dict[str, float], dict[str, float], list[str], dict[str, str]]:
        """
        全账户配仓：若类内产品触顶导致可落地额低于大类目标，则冻结该类并重算其余类。
        """
        max_rounds = int(self.solver.get("max_iterations", 10))
        frozen_overrides: dict[str, float] = dict(overrides)
        frozen_locked: set[str] = set(locked) | set(overrides.keys())
        freeze_notes: list[str] = []
        priority = self._freeze_priority(categories)

        target_cat: dict[str, float] = {}
        product_targets: dict[str, float] = {}
        alloc_notes: list[str] = []
        limit_hits: dict[str, str] = {}

        for _ in range(max(1, max_rounds)):
            target_cat = self._solve_category_targets(
                total=total,
                current_cat=current_cat,
                profile_targets=profile_targets,
                locked=frozen_locked,
                overrides=frozen_overrides,
                target_category=None,
                categories=categories,
            )
            product_targets, alloc_notes, limit_hits = allocate_fn(target_cat)
            actual_cat = aggregate_fn(product_targets)

            shortfalls: list[str] = []
            for cat in categories:
                if cat in frozen_overrides:
                    continue
                desired = target_cat.get(cat, 0.0)
                actual = actual_cat.get(cat, 0.0)
                if desired - actual > 0.01:
                    shortfalls.append(cat)

            if not shortfalls:
                break

            progressed = False
            for cat in priority:
                if cat not in shortfalls:
                    continue
                actual = actual_cat.get(cat, 0.0)
                if cat in frozen_overrides and abs(frozen_overrides[cat] - actual) < 0.01:
                    continue
                if cat not in frozen_overrides:
                    label = cat_names.get(cat, cat)
                    freeze_notes.append(
                        f"{label}因产品触顶，已冻结在可落地金额{actual:,.0f}元，"
                        f"其余{'资产类型' if set(categories) == set(INVESTMENT_CARD_KEYS) else '大类'}已重新求解"
                    )
                frozen_overrides[cat] = round(actual, 2)
                frozen_locked.add(cat)
                progressed = True

            if not progressed:
                break

        return target_cat, product_targets, freeze_notes + alloc_notes, limit_hits

    @staticmethod
    def _held_products(
        prods: list[dict[str, Any]],
        current_holdings: dict[str, float],
        threshold: float = 0.01,
    ) -> list[dict[str, Any]]:
        """仅保留当前有持仓的候选产品（智能配仓不参与 0 持仓候选）。"""
        return [
            p for p in prods
            if current_holdings.get(p["code"], 0.0) > threshold
        ]

    def _allocate_products(
        self,
        target_cat: dict[str, float],
        current_holdings: dict[str, float],
        prefer_existing: bool,
        consolidate: bool = False,
        only_category: str | None = None,
        product_index: dict[str, list[dict[str, Any]]] | None = None,
        cat_names: dict[str, str] | None = None,
    ) -> tuple[dict[str, float], list[str], dict[str, str]]:
        """将大类目标分配到底层产品（仅已有持仓产品参与分配与 spill）。"""
        result: dict[str, float] = {}
        notes: list[str] = []
        limit_hits: dict[str, str] = {}
        index = product_index or self.by_category
        names = cat_names or get_category_names()
        for cat, cat_target in target_cat.items():
            prods = index.get(cat, [])
            if not prods:
                continue

            if only_category and cat != only_category:
                for p in self._held_products(prods, current_holdings):
                    result[p["code"]] = round(current_holdings.get(p["code"], 0.0), 2)
                continue

            held_prods = self._held_products(prods, current_holdings)
            if not held_prods:
                notes.append(
                    f"{names.get(cat, cat)}当前无持仓产品，未生成产品调仓建议"
                )
                continue

            if consolidate:
                cat_result, cat_notes, cat_limits = self._allocate_category_consolidated(
                    cat=cat,
                    cat_target=cat_target,
                    prods=held_prods,
                    current_holdings=current_holdings,
                    cat_names=names,
                )
                result.update(cat_result)
                notes.extend(cat_notes)
                limit_hits.update(cat_limits)
                continue

            current_in_cat = {
                p["code"]: current_holdings.get(p["code"], 0.0) for p in held_prods
            }
            equal_w = 1.0 / len(held_prods)
            seed: dict[str, float] = {}

            if prefer_existing and sum(current_in_cat.values()) > 0:
                cat_current_total = sum(current_in_cat.values())
                for p in held_prods:
                    code = p["code"]
                    ratio = current_in_cat[code] / cat_current_total
                    seed[code] = cat_target * ratio
            else:
                for p in held_prods:
                    code = p["code"]
                    seed[code] = cat_target * equal_w

            cat_result, cat_notes, cat_limits = self._allocate_with_spillover(
                cat=cat,
                cat_target=cat_target,
                prods=held_prods,
                seed=seed,
                current_holdings=current_holdings,
                cat_names=names,
            )
            result.update(cat_result)
            notes.extend(cat_notes)
            limit_hits.update(cat_limits)

        return result, notes, limit_hits

    @staticmethod
    def _pick_rebalance_product(prods: list[dict[str, Any]]) -> dict[str, Any]:
        """调仓优先级档数越低越优先，档数相同按产品 code 字典序。"""
        return sorted(
            prods,
            key=lambda p: (p.get("rebalance_priority", 3), p["code"]),
        )[0]

    def _allocate_category_consolidated(
        self,
        cat: str,
        cat_target: float,
        prods: list[dict[str, Any]],
        current_holdings: dict[str, float],
        cat_names: dict[str, str] | None = None,
    ) -> tuple[dict[str, float], list[str], dict[str, str]]:
        """
        类内单产品集中调仓：优先产品承接大类增减；触达上下限时差额由其他产品按优先级承接。
        """
        primary = self._pick_rebalance_product(prods)
        primary_code = primary["code"]
        others_current = sum(
            current_holdings.get(p["code"], 0.0)
            for p in prods
            if p["code"] != primary_code
        )
        seed: dict[str, float] = {}
        for p in prods:
            code = p["code"]
            if code == primary_code:
                seed[code] = cat_target - others_current
            else:
                seed[code] = current_holdings.get(code, 0.0)

        return self._allocate_with_spillover(
            cat=cat,
            cat_target=cat_target,
            prods=prods,
            seed=seed,
            current_holdings=current_holdings,
            primary_name=primary["name"],
            primary_code=primary_code,
            cat_names=cat_names,
        )

    def _product_min(self, code: str) -> float:
        if not self._product_limits_enabled():
            return 0.0
        return self.products[code].get("min_amount", 0)

    def _product_max(self, code: str) -> float:
        if not self._product_limits_enabled():
            return float("inf")
        return self.products[code].get("max_amount", float("inf"))

    def _allocate_with_spillover(
        self,
        cat: str,
        cat_target: float,
        prods: list[dict[str, Any]],
        seed: dict[str, float],
        current_holdings: dict[str, float] | None = None,
        primary_name: str | None = None,
        primary_code: str | None = None,
        cat_names: dict[str, str] | None = None,
    ) -> tuple[dict[str, float], list[str], dict[str, str]]:
        """按优先级分配类目标；单产品触达上下限后，将剩余差额 spill 到其他产品。"""
        notes: list[str] = []
        limit_hits: dict[str, str] = {}
        names = cat_names or get_category_names()
        ordered = sorted(
            prods, key=lambda p: (p.get("rebalance_priority", 3), p["code"])
        )
        holdings = current_holdings or {}
        result: dict[str, float] = {}
        for p in prods:
            code = p["code"]
            raw = seed.get(code, 0.0)
            cur = holdings.get(code, 0.0)
            if primary_code and code != primary_code:
                clamped = round(raw, 2)
            else:
                clamped = round(self._clamp_product(code, raw, current=cur), 2)
            result[code] = clamped
            if raw > self._product_max(code) + 0.01:
                limit_hits[code] = "max"
        gap = round(cat_target - sum(result.values()), 2)

        while gap > 0.01:
            progressed = False
            for p in ordered:
                if gap <= 0.01:
                    break
                code = p["code"]
                room = round(self._product_max(code) - result[code], 2)
                if room <= 0.01:
                    continue
                add = min(gap, room)
                result[code] = round(result[code] + add, 2)
                gap = round(gap - add, 2)
                if abs(result[code] - self._product_max(code)) < 0.01 and gap > 0.01:
                    limit_hits[code] = "max"
                progressed = True
            if not progressed:
                if gap > 0.01:
                    for p in ordered:
                        code = p["code"]
                        if abs(result[code] - self._product_max(code)) < 0.01:
                            limit_hits[code] = "max"
                break

        while gap < -0.01:
            progressed = False
            for p in reversed(ordered):
                if gap >= -0.01:
                    break
                code = p["code"]
                room = self._sellable_room(code, result[code])
                if room <= 0.01:
                    continue
                cut = min(-gap, room)
                result[code] = round(result[code] - cut, 2)
                gap = round(gap + cut, 2)
                progressed = True
            if not progressed:
                break

        if self._snap_sub_minimum_holdings(result, prods, limit_hits, holdings):
            gap = round(cat_target - sum(result.values()), 2)
            while gap > 0.01:
                progressed = False
                for p in ordered:
                    if gap <= 0.01:
                        break
                    code = p["code"]
                    room = round(self._product_max(code) - result[code], 2)
                    if room <= 0.01:
                        continue
                    add = min(gap, room)
                    result[code] = round(result[code] + add, 2)
                    gap = round(gap - add, 2)
                    if abs(result[code] - self._product_max(code)) < 0.01 and gap > 0.01:
                        limit_hits[code] = "max"
                    progressed = True
                if not progressed:
                    break

        self._tag_category_liquidations(result, prods, holdings, limit_hits)
        self._tag_product_max_limits(result, prods, limit_hits)

        cat_actual = round(sum(result.values()), 2)
        if abs(gap) > 0.01:
            lead = primary_name or ordered[0]["name"]
            notes.append(
                f"{names.get(cat, cat)}内由{lead}优先配置，"
                f"部分产品已达金额上下限，差额已按优先级调整至其他产品，"
                f"实际配置{cat_actual:,.0f}元（目标{cat_target:,.0f}元）"
            )
        return result, notes, limit_hits

    def _liquidate_below_min(self) -> bool:
        return bool(self.solver.get("liquidate_below_min", False))

    def _sellable_room(self, code: str, amount: float) -> float:
        if self._liquidate_below_min():
            return round(max(amount, 0.0), 2)
        return round(amount - self._product_min(code), 2)

    def _snap_sub_minimum_holdings(
        self,
        result: dict[str, float],
        prods: list[dict[str, Any]],
        limit_hits: dict[str, str],
        current_holdings: dict[str, float] | None = None,
    ) -> bool:
        """低于 min 的碎片持仓清仓为 0（liquidate_below_min 开启时）。"""
        if not self._liquidate_below_min():
            return False
        holdings = current_holdings or {}
        changed = False
        for p in prods:
            code = p["code"]
            mn = self._product_min(code)
            amt = result.get(code, 0.0)
            cur = holdings.get(code, 0.0)
            # 已有持仓允许低于起购额继续持有，不因 min 被迫清仓
            if cur > 0.01 and amt > 0.01:
                continue
            if 0 < amt < mn - 0.01:
                result[code] = 0.0
                changed = True
        return changed

    def _tag_category_liquidations(
        self,
        result: dict[str, float],
        prods: list[dict[str, Any]],
        current_holdings: dict[str, float],
        limit_hits: dict[str, str],
    ) -> None:
        """有持仓被类内调仓清至 0 时标记 liquidate（与触顶 max 区分）。"""
        for p in prods:
            code = p["code"]
            if limit_hits.get(code) == "max":
                continue
            cur = current_holdings.get(code, 0.0)
            tgt = result.get(code, 0.0)
            if cur > 0.01 and tgt <= 0.01:
                limit_hits[code] = "liquidate"

    def _tag_product_max_limits(
        self,
        result: dict[str, float],
        prods: list[dict[str, Any]],
        limit_hits: dict[str, str],
    ) -> None:
        """目标金额配满至产品上限时统一标记 max（含 spill 恰好填满的情形）。"""
        if not self._product_limits_enabled():
            return
        for p in prods:
            code = p["code"]
            if limit_hits.get(code):
                continue
            amt = result.get(code, 0.0)
            mx = self._product_max(code)
            if amt > 0.01 and mx < float("inf") and abs(amt - mx) < 0.01:
                limit_hits[code] = "max"

    def _limit_side(
        self, code: str, raw: float, current: float = 0.0
    ) -> str | None:
        if not self._product_limits_enabled():
            return None
        if raw > self._product_max(code) + 0.01:
            return "max"
        return None

    def _clamp_product(
        self, code: str, amount: float, current: float = 0.0
    ) -> float:
        raw = max(0.0, float(amount))
        if not self._product_limits_enabled():
            return round(raw, 2)
        mn = self._product_min(code)
        mx = self._product_max(code)
        # 已有持仓：不因低于起购额被强制清仓或抬升至 min
        if current > 0.01:
            if raw <= 0.01:
                return 0.0
            return round(min(raw, mx), 2)
        if raw <= 0.01:
            return 0.0
        if self._liquidate_below_min() and raw < mn - 0.01:
            return 0.0
        if raw < mn - 0.01:
            return round(min(mn, mx), 2)
        return round(min(raw, mx), 2)

    def _build_deltas(
        self,
        current: dict[str, float],
        targets: dict[str, float],
        limit_hits: dict[str, str] | None = None,
        include_target_codes: bool = False,
        use_asset_type_key: bool = False,
    ) -> list[ProductDelta]:
        deltas = []
        if include_target_codes:
            all_codes = sorted(
                set(targets.keys())
                | {code for code, amt in current.items() if amt > 0.01}
            )
        else:
            all_codes = sorted(
                code for code, amt in current.items() if amt > 0.01
            )
        for code in all_codes:
            prod = self.products.get(code)
            if not prod:
                continue
            cur = current.get(code, 0.0)
            tgt = targets.get(code, cur)
            delta = round(tgt - cur, 2)
            action = "hold" if abs(delta) < 0.01 else ("buy" if delta > 0 else "sell")
            side = (limit_hits or {}).get(code, "")
            cat_key = (
                prod.get("asset_type", "")
                if use_asset_type_key
                else prod.get("category", "")
            )
            deltas.append(
                ProductDelta(
                    product_code=code,
                    product_name=prod["name"],
                    category=cat_key,
                    current_amount=cur,
                    target_amount=tgt,
                    delta_amount=delta,
                    action=action,
                    limit_hit=bool(side),
                    limit_side=side,
                )
            )
        return deltas

    def _build_category_summary(
        self,
        total: float,
        current_cat: dict[str, float],
        target_cat: dict[str, float],
        profile_targets: dict[str, Any],
        categories: list[str] | None = None,
        names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        cats = categories or self.categories
        display_names = names or get_category_names()
        summary = []
        for cat in cats:
            cur = current_cat.get(cat, 0.0)
            tgt = target_cat.get(cat, 0.0)
            band = profile_targets[cat]["band"]
            final_ratio = tgt / total if total else 0
            in_band = band[0] <= final_ratio <= band[1]
            summary.append(
                {
                    "category": cat,
                    "category_name": display_names.get(cat, cat),
                    "target_ratio": profile_targets[cat]["target"],
                    "current_ratio": cur / total if total else 0,
                    "final_ratio": final_ratio,
                    "current_amount": round(cur, 2),
                    "target_amount": round(tgt, 2),
                    "adjust_amount": round(tgt - cur, 2),
                    "band": band,
                    "in_band": in_band,
                }
            )
        return summary

    def _validate(
        self,
        total: float,
        target_cat: dict[str, float],
        profile_targets: dict[str, Any],
        deltas: list[ProductDelta],
        categories: list[str] | None = None,
        names: dict[str, str] | None = None,
    ) -> list[str]:
        cats = categories or self.categories
        display_names = names or get_category_names()
        notes: list[str] = []
        constraint = load_page_constraint()
        max_single = constraint.get("full_account_optimize", {}).get("max_single_product_ratio", 0.4)

        for cat in cats:
            ratio = target_cat[cat] / total if total else 0
            band = profile_targets[cat]["band"]
            label = display_names.get(cat, cat)
            if ratio < band[0]:
                notes.append(f"{label}最终占比{ratio:.1%}低于模型下限{band[0]:.1%}，已取次优解")
            elif ratio > band[1]:
                notes.append(f"{label}最终占比{ratio:.1%}高于模型上限{band[1]:.1%}，已取次优解")

        for d in deltas:
            if d.target_amount / total > max_single:
                notes.append(f"{d.product_name}目标占比超过单产品上限{max_single:.0%}")

        if not notes:
            notes.append("配置方案已落在模型区间内，校验通过")
        return notes

    def _resolve_fallback_target(
        self,
        fallback: str,
        ideal: float,
        lo: float,
        hi: float,
    ) -> float:
        """大类占比越界时的回退落点（minimize_cash_movement=true 时生效）。"""
        if fallback == "benchmark":
            return self._clamp(ideal, lo, hi)
        if fallback == "band_low":
            return lo
        if fallback == "band_high":
            return hi
        if fallback == "band_midpoint":
            return (lo + hi) / 2
        # 未知策略时回退到区间中点
        return (lo + hi) / 2

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(value, hi))


def compute_health_level(max_deviation: float) -> tuple[str, str, str]:
    """根据最大偏差返回健康度等级、标签、颜色。"""
    page = load_four_money_page()
    thresholds = page.get("health_thresholds", {})
    if max_deviation <= thresholds.get("green", {}).get("max_deviation", 0.05):
        g = thresholds["green"]
        return "green", g["label"], g["color"]
    if max_deviation <= thresholds.get("yellow", {}).get("max_deviation", 0.12):
        y = thresholds["yellow"]
        return "yellow", y["label"], y["color"]
    r = thresholds["red"]
    return "red", r["label"], r["color"]
