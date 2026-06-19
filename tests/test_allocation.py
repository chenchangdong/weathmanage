"""Tests for four-money asset allocation."""

import pytest

from agent_core.explain_agent import ExplainAgent
from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine, compute_health_level
from core.asset_service import AssetOverviewService
from core.config_loader import (
    get_asset_type_to_category,
    get_demo_customer,
    get_product_map,
    load_four_money_rule,
    load_product_constraint,
)
from core.data_store import get_customer_holdings


CUSTOMER_ID = "C20250602001"
FOUR_MONEY_PLANNING = "综合规划"
INVESTMENT_PLANNING = "投资规划"


def _enable_product_limit_validation(monkeypatch) -> None:
    monkeypatch.setattr(
        "asset_allocation.auto_rebalance_engine.is_product_limit_validation_enabled",
        lambda: True,
    )


class TestConfigLoader:
    def test_four_money_rule_loaded(self):
        rule = load_four_money_rule()
        assert "categories" in rule
        assert len(rule["categories"]) == 4
        assert "solver" in rule
        assert "risk_profiles" not in rule

    def test_product_constraint_loaded(self):
        pc = load_product_constraint()
        assert len(pc["products"]) >= 8
        assert "category_product_weights" not in pc
        assert "asset_types" in pc

    def test_product_asset_type_to_four_money(self):
        mapping = get_asset_type_to_category()
        assert mapping["cash"] == "spend"
        assert mapping["fixed_income"] == "preserve"
        assert mapping["equity"] == "grow"
        assert mapping["alternative"] == "grow"
        assert mapping["insurance"] == "protect"
        pmap = get_product_map()
        assert pmap["001"]["asset_type"] == "cash"
        assert pmap["001"]["four_money_category"] == "spend"
        assert pmap["004"]["asset_type"] == "fixed_income"
        assert pmap["004"]["four_money_category"] == "preserve"
        assert pmap["011"]["asset_type"] == "alternative"
        assert pmap["011"]["four_money_category"] == "grow"

    def test_demo_customer_exists(self):
        c = get_demo_customer(CUSTOMER_ID)
        assert c is not None
        assert c["risk_profile"] in (
            "conservative", "prudent", "balanced", "growth", "aggressive"
        )


class TestAutoRebalanceEngine:
    def setup_method(self):
        self.engine = AutoRebalanceEngine()
        self.data = get_customer_holdings(CUSTOMER_ID)
        self.customer = get_demo_customer(CUSTOMER_ID)

    def test_full_rebalance(self):
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        assert result.total_assets > 0
        assert len(result.category_summary) == 4
        assert len(result.product_deltas) > 0
        assert len(result.validation_notes) > 0

    def test_category_summary_matches_product_targets(self):
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        cat_sum = sum(result.category_targets.values())
        prod_sum = sum(d.target_amount for d in result.product_deltas)
        assert abs(cat_sum - prod_sum) < 1.0
        for s in result.category_summary:
            prod_tgt = sum(
                d.target_amount for d in result.product_deltas if d.category == s["category"]
            )
            prod_adj = sum(
                d.delta_amount for d in result.product_deltas if d.category == s["category"]
            )
            assert abs(s["target_amount"] - prod_tgt) < 1.0
            assert abs(s["adjust_amount"] - prod_adj) < 1.0

    def test_single_category_optimize(self):
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            target_category="grow",
        )
        assert result.category_targets["grow"] >= 0

    def test_single_category_freezes_other_categories(self):
        """单类优化仅调整目标大类，其余大类保持当前持仓不变。"""
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            target_category="grow",
        )
        for s in result.category_summary:
            if s["category"] != "grow":
                assert abs(s["adjust_amount"]) < 1.0
                assert abs(s["target_amount"] - s["current_amount"]) < 1.0
        grow_adj = next(
            s["adjust_amount"] for s in result.category_summary if s["category"] == "grow"
        )
        assert abs(grow_adj) > 1.0
        for d in result.product_deltas:
            if d.category != "grow":
                assert abs(d.delta_amount) < 1.0

    def test_single_category_reduce_over_allocated_grow(self):
        """超配大类单类优化应减配至模型基准值，而非抬升占比。"""
        total = sum(self.data["holdings"].values()) + self.data["idle_cash"]
        engine = AutoRebalanceEngine()
        resolved = engine.config_svc.resolve_profile_targets(
            FOUR_MONEY_PLANNING, self.customer["risk_profile"]
        )
        benchmark = resolved["targets"]["grow"]["target"] * total
        result = engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            target_category="grow",
        )
        grow = next(s for s in result.category_summary if s["category"] == "grow")
        assert grow["adjust_amount"] < -1.0
        assert grow["final_ratio"] < grow["current_ratio"]
        assert grow["final_ratio"] <= grow["band"][1] + 0.001
        assert abs(grow["target_amount"] - benchmark) < total * 0.05
        for s in result.category_summary:
            if s["category"] != "grow":
                assert abs(s["adjust_amount"]) < 1.0
        assert any("单类优化仅调整" in n for n in result.validation_notes)
        grow_deltas = [d for d in result.product_deltas if d.category == "grow"]
        assert sum(d.delta_amount for d in grow_deltas) < -1.0

    def test_consolidate_category_rebalance(self, monkeypatch):
        """开启类内集中调仓后，每大类仅优先持仓产品发生买卖。"""
        _enable_product_limit_validation(monkeypatch)
        engine = AutoRebalanceEngine()
        engine.solver["consolidate_category_rebalance"] = True
        result = engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        pmap = get_product_map()
        holdings = self.data["holdings"]
        for cat in ("spend", "preserve"):
            prods = [
                p for p in pmap.values() if p.get("four_money_category") == cat
            ]
            held = AutoRebalanceEngine._held_products(prods, holdings)
            if not held:
                continue
            primary = AutoRebalanceEngine._pick_rebalance_product(held)
            active = [
                d for d in result.product_deltas
                if d.category == cat and d.action in ("buy", "sell")
            ]
            if not active:
                continue
            assert len(active) == 1
            assert active[0].product_code == primary["code"]

    def test_exclude_zero_holding_products(self):
        """智能配仓不向 0 持仓候选分配，方案与明细均不展示未持仓产品。"""
        data = get_customer_holdings("C20250602002")
        customer = get_demo_customer("C20250602002")
        result = AutoRebalanceEngine().rebalance(
            customer_id="C20250602002",
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        codes = {d.product_code for d in result.product_deltas}
        assert "008" not in codes
        assert "007" not in codes
        assert "011" not in codes
        for d in result.product_deltas:
            assert d.current_amount > 0
        grow_active = [
            d for d in result.product_deltas
            if d.category == "grow" and d.action in ("buy", "sell")
        ]
        assert len(grow_active) == 1
        assert grow_active[0].product_code == "006"

        zhang = get_customer_holdings(CUSTOMER_ID)
        zhang_result = AutoRebalanceEngine().rebalance(
            customer_id=CUSTOMER_ID,
            holdings=zhang["holdings"],
            idle_cash=zhang["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        zhang_codes = {d.product_code for d in zhang_result.product_deltas}
        assert "005" not in zhang_codes
        assert "011" not in zhang_codes

    def test_limit_spillover_to_sibling_products(self, monkeypatch):
        """优先产品触达 max_amount 后，差额由同大类其他产品按优先级承接。"""
        _enable_product_limit_validation(monkeypatch)
        data = get_customer_holdings("C20250602002")
        customer = get_demo_customer("C20250602002")
        engine = AutoRebalanceEngine()
        engine.solver["consolidate_category_rebalance"] = True
        result = engine.rebalance(
            customer_id="C20250602002",
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        protect = {d.product_code: d for d in result.product_deltas if d.category == "protect"}
        assert protect["009"].target_amount == 100000
        assert protect["010"].target_amount == 5000
        assert protect["010"].delta_amount == 4000
        assert protect["009"].limit_hit is True
        assert protect["009"].limit_side == "max"
        assert protect["010"].limit_hit is True
        assert protect["010"].limit_side == "max"
        assert any(
            ("保障的钱" in n and "其他产品" in n)
            or ("保障的钱" in n and "冻结" in n)
            for n in result.validation_notes
        )

    def test_consolidate_priority_tiebreak_by_code(self):
        prods = [
            {"code": "002", "rebalance_priority": 1},
            {"code": "001", "rebalance_priority": 1},
        ]
        picked = AutoRebalanceEngine._pick_rebalance_product(prods)
        assert picked["code"] == "001"

    def test_manual_sell_to_zero_shows_liquidate_tag(self):
        """二次调仓将持仓产品减至 0 应标记类内调仓清仓。"""
        base = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        baseline = {d.product_code: d.target_amount for d in base.product_deltas}
        result = self.engine.apply_manual_product_targets(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            product_targets={"008": 0},
            baseline_product_targets=baseline,
        )
        p008 = next(d for d in result.product_deltas if d.product_code == "008")
        assert p008.target_amount == 0
        assert p008.action == "sell"
        assert p008.limit_hit is True
        assert p008.limit_side == "liquidate"

    def test_category_liquidate_tags_all_cleared_holdings(self):
        """类内调仓清仓时，被清至 0 的持仓产品均应标记 liquidate。"""
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        by_code = {d.product_code: d for d in result.product_deltas}
        for code in ("007", "008"):
            assert by_code[code].target_amount == 0
            assert by_code[code].limit_hit is True
            assert by_code[code].limit_side == "liquidate"

    def test_freeze_reroutes_when_category_hits_product_max(self, monkeypatch):
        """保障类触顶冻结后，溢出应通过大类重算落到其余类，且产品目标凑满总资产。"""
        _enable_product_limit_validation(monkeypatch)
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        deployed = sum(d.target_amount for d in result.product_deltas)
        assert abs(deployed - result.total_assets) < 1.0
        protect = {d.product_code: d for d in result.product_deltas if d.category == "protect"}
        assert sum(protect[c].target_amount for c in protect) == 105_000
        assert protect["009"].limit_hit is True
        assert protect["009"].limit_side == "max"
        assert protect["010"].limit_hit is True
        assert protect["010"].limit_side == "max"
        spend = sum(d.target_amount for d in result.product_deltas if d.category == "spend")
        assert spend > 50_000
        assert any("冻结" in n for n in result.validation_notes)

    def test_manual_adjust_revalidates_all_product_limits(self):
        """调整 A 产品时，方案内其他产品的上下限也应重新校验。"""
        base = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        baseline = {d.product_code: d.target_amount for d in base.product_deltas}
        baseline["005"] = 20.0
        p004 = next(d for d in base.product_deltas if d.product_code == "004")

        result = self.engine.apply_manual_product_targets(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            product_targets={p004.product_code: p004.target_amount},
            baseline_product_targets=baseline,
        )
        p005 = next(d for d in result.product_deltas if d.product_code == "005")
        assert p005.limit_hit is False
        assert p005.limit_side == ""

    def test_manual_adjust_adds_zero_holding_product(self):
        """二次调仓可从候选新增 0 持仓产品并参与联动计算。"""
        base = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        baseline = {d.product_code: d.target_amount for d in base.product_deltas}
        baseline["005"] = 0.0

        result = self.engine.apply_manual_product_targets(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            product_targets={"005": 200_000.0},
            baseline_product_targets=baseline,
        )
        p005 = next(d for d in result.product_deltas if d.product_code == "005")
        assert p005.current_amount == 0.0
        assert p005.target_amount == 200_000.0
        assert p005.delta_amount == 200_000.0
        assert p005.action == "buy"

    def test_manual_product_adjust(self):
        base = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        code = base.product_deltas[0].product_code
        before = {d.product_code: d for d in base.product_deltas}
        new_target = before[code].target_amount + 50000

        baseline = {d.product_code: d.target_amount for d in base.product_deltas}
        result = self.engine.apply_manual_product_targets(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            product_targets={code: new_target},
            baseline_product_targets=baseline,
        )
        assert result.mode == "manual_product_edit"
        changed = next(d for d in result.product_deltas if d.product_code == code)
        assert changed.target_amount >= new_target - 1 or changed.target_amount <= new_target
        for d in result.product_deltas:
            if d.product_code != code:
                assert d.target_amount == before[d.product_code].target_amount
        assert len(result.category_summary) == 4
        assert any("不一致" in n or "次优解" in n or "校验通过" in n or "超过" in n
                   for n in result.validation_notes)

    def test_liquidate_below_min(self, monkeypatch):
        """开启 liquidate_below_min 后，0 持仓新配低于 min 清仓；已有持仓可低于 min 继续持有。"""
        _enable_product_limit_validation(monkeypatch)
        from core.config_loader import get_products_by_category

        engine = AutoRebalanceEngine()
        engine.solver["liquidate_below_min"] = False
        assert engine._clamp_product("003", 3000) == 5000
        assert engine._clamp_product("003", 8000) == 8000

        engine.solver["liquidate_below_min"] = True
        assert engine._clamp_product("003", 3000) == 0
        assert engine._clamp_product("003", 0) == 0
        assert engine._clamp_product("003", 8000) == 8000
        # 大额存单 min=20万，已有 10 万持仓不因低于起购额被迫清仓
        assert engine._clamp_product("005", 100_000, current=100_000) == 100_000

        prods = get_products_by_category()["preserve"]
        result, _, hits = engine._allocate_with_spillover(
            cat="preserve",
            cat_target=200_000,
            prods=prods,
            seed={"003": 3_000, "004": 150_000, "005": 47_000},
        )
        assert result["003"] == 0
        assert hits.get("003") is None
        assert abs(sum(result.values()) - 200_000) < 1.0

    def test_product_limit_validation_disabled_skips_min_max(self):
        engine = AutoRebalanceEngine()
        assert engine._clamp_product("003", 3000) == 3000
        assert engine._clamp_product("003", 8_000_000) == 8_000_000

    def test_product_limit_validation_enabled_clamps_min_max(self, monkeypatch):
        _enable_product_limit_validation(monkeypatch)
        engine = AutoRebalanceEngine()
        engine.solver["liquidate_below_min"] = False
        assert engine._clamp_product("003", 3000) == 5000
        assert engine._clamp_product("003", 8_000_000) == 1_000_000

    def test_existing_holding_below_min_not_forced_sell(self):
        """已有持仓低于起购额时，综合规划不应卖出转投同类产品。"""
        data = get_customer_holdings("C20250602002")
        customer = get_demo_customer("C20250602002")
        result = AutoRebalanceEngine().rebalance(
            customer_id="C20250602002",
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        preserve = {d.product_code: d for d in result.product_deltas if d.category == "preserve"}
        assert preserve["005"].action == "hold"
        assert preserve["005"].target_amount == 100_000
        assert preserve["004"].delta_amount < 0
        assert abs(preserve["004"].delta_amount) < 10_000

    def test_fallback_strategy_benchmark(self):
        """越界回退为 benchmark 时，落点取模型基准（裁剪到区间内）。"""
        engine = AutoRebalanceEngine()
        assert engine._resolve_fallback_target("benchmark", 150_000, 100_000, 210_000) == 150_000
        assert engine._resolve_fallback_target("benchmark", 500_000, 400_000, 600_000) == 500_000
        assert engine._resolve_fallback_target("benchmark", 650_000, 400_000, 600_000) == 600_000
        assert engine._resolve_fallback_target("benchmark", 80_000, 100_000, 210_000) == 100_000
        assert engine._resolve_fallback_target("band_midpoint", 150_000, 100_000, 210_000) == 155_000

        engine.solver["fallback_strategy"] = "benchmark"
        engine.solver["minimize_cash_movement"] = True
        total = 1_000_000.0
        profile_targets = {
            "spend": {"target": 0.15, "band": [0.10, 0.21]},
            "preserve": {"target": 0.25, "band": [0.20, 0.30]},
            "grow": {"target": 0.50, "band": [0.40, 0.60]},
            "protect": {"target": 0.10, "band": [0.05, 0.15]},
        }
        current_cat = {
            "spend": 80_000.0,
            "preserve": 250_000.0,
            "grow": 500_000.0,
            "protect": 100_000.0,
        }
        target = engine._solve_category_targets(
            total=total,
            current_cat=current_cat,
            profile_targets=profile_targets,
            locked=set(),
            overrides={},
            target_category=None,
        )
        assert abs(target["spend"] - 150_000.0) < 1.0

    def test_manual_tweak_mode(self):
        total = sum(self.data["holdings"].values()) + self.data["idle_cash"]
        result = self.engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=self.data["holdings"],
            idle_cash=self.data["idle_cash"],
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            mode="manual_tweak",
            manual_overrides={"spend": total * 0.12},
            locked_categories=["spend"],
        )
        assert result.mode == "manual_tweak"
        assert "spend" in result.locked_categories


class TestIdleCashAddon:
    """追加持仓并入活钱大类 current（投资规划→cash，综合规划→spend）。"""

    ADDON = 100_000.0

    def setup_method(self):
        self.engine = AutoRebalanceEngine()
        self.customer_id = "C20250602002"
        self.data = get_customer_holdings(self.customer_id)
        self.customer = get_demo_customer(self.customer_id)

    def test_investment_addon_absorbed_by_cash_when_in_band(self):
        base = self.engine.rebalance(
            customer_id=self.customer_id,
            holdings=self.data["holdings"],
            idle_cash=0,
            risk_profile=self.customer["risk_profile"],
            product_category=INVESTMENT_PLANNING,
            loss_key="loss_3pct",
        )
        result = self.engine.rebalance(
            customer_id=self.customer_id,
            holdings=self.data["holdings"],
            idle_cash=self.ADDON,
            risk_profile=self.customer["risk_profile"],
            product_category=INVESTMENT_PLANNING,
            loss_key="loss_3pct",
        )
        cash_base = next(s for s in base.category_summary if s["category"] == "cash")
        cash = next(s for s in result.category_summary if s["category"] == "cash")
        assert cash["current_amount"] == pytest.approx(
            cash_base["current_amount"] + self.ADDON, abs=0.01
        )
        assert cash["target_amount"] == pytest.approx(cash["current_amount"], abs=0.01)
        for cat in ("fixed_income", "equity", "alternative"):
            row = next(s for s in result.category_summary if s["category"] == cat)
            base_row = next(s for s in base.category_summary if s["category"] == cat)
            assert row["adjust_amount"] == pytest.approx(0, abs=0.01)
            assert row["target_amount"] == pytest.approx(base_row["target_amount"], abs=0.01)

    def test_four_money_spend_current_includes_addon(self):
        spend_holdings = sum(
            amt
            for code, amt in self.data["holdings"].items()
            if get_product_map()[code]["four_money_category"] == "spend"
        )
        result = self.engine.rebalance(
            customer_id=self.customer_id,
            holdings=self.data["holdings"],
            idle_cash=self.ADDON,
            risk_profile=self.customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
            loss_key="loss_3pct",
        )
        spend = next(s for s in result.category_summary if s["category"] == "spend")
        assert spend["current_amount"] == pytest.approx(
            spend_holdings + self.ADDON, abs=0.01
        )
        assert result.total_assets == pytest.approx(
            sum(self.data["holdings"].values()) + self.ADDON, abs=0.01
        )


class TestHealthLevel:
    def test_green_when_in_band(self):
        level, label, color = compute_health_level(True)
        assert level == "green"
        assert label == "配置健康"

    def test_red_when_out_of_band(self):
        level, label, color = compute_health_level(False)
        assert level == "red"
        assert label == "需优化"


class TestAssetOverview:
    def test_build_overview_investment(self):
        svc = AssetOverviewService()
        overview = svc.build_overview(CUSTOMER_ID, product_category=INVESTMENT_PLANNING)
        assert overview.customer_id == CUSTOMER_ID
        assert overview.view_mode == "asset_type"
        assert overview.total_assets == 862000.0 - 32000.0
        assert len(overview.categories) == 4
        assert overview.health_level in ("green", "red")

    def test_conservative_investment_all_in_band_is_green(self):
        """李先生投资规划：各类均在模型区间内时应为配置健康。"""
        svc = AssetOverviewService()
        overview = svc.build_overview("C20250602002", product_category=INVESTMENT_PLANNING)
        assert all(c.in_band for c in overview.categories)
        assert overview.health_level == "green"
        assert overview.health_label == "配置健康"

    def test_build_overview_comprehensive(self):
        svc = AssetOverviewService()
        overview = svc.build_overview(CUSTOMER_ID, product_category=FOUR_MONEY_PLANNING)
        assert overview.view_mode == "four_money"
        assert overview.total_assets > 0
        assert len(overview.categories) == 4

    def test_overview_excludes_zero_holdings(self):
        """资产检视不展示 0 持仓产品。"""
        svc = AssetOverviewService()
        overview = svc.build_overview(CUSTOMER_ID, product_category=INVESTMENT_PLANNING)
        all_codes = {
            p["code"]
            for c in overview.categories
            for p in c.products
        }
        assert "005" not in all_codes
        assert "011" not in all_codes
        for c in overview.categories:
            for p in c.products:
                assert p["amount"] > 0


class TestExplainAgent:
    def test_generate_explanation(self):
        engine = AutoRebalanceEngine()
        data = get_customer_holdings(CUSTOMER_ID)
        customer = get_demo_customer(CUSTOMER_ID)
        result = engine.rebalance(
            customer_id=CUSTOMER_ID,
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        explain = ExplainAgent().generate(result)
        assert "四笔钱" in explain["allocation_logic"]
        assert "allocation_logic" in explain
        assert "over_under_reason" in explain
        assert "customer_fit" in explain
        assert "client_script" in explain
        assert len(explain["allocation_logic"]) > 50

