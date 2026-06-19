"""Tests for demand deposit (P000) display layer."""

import pytest

from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine
from core.config_loader import get_demo_customer, get_product_map
from core.data_store import get_customer_holdings
from core.product_display import (
    DEMAND_DEPOSIT_CODE,
    apply_demand_deposit_display,
    apply_demand_deposit_to_result,
)

FOUR_MONEY_PLANNING = "综合规划"
INVESTMENT_PLANNING = "投资规划"


class TestDemandDepositDisplay:
    def test_p013_is_highest_priority_product(self):
        pmap = get_product_map()
        assert DEMAND_DEPOSIT_CODE in pmap
        assert pmap["000"]["name"] == "活钱存款"
        assert pmap["000"]["rebalance_priority"] < pmap["001"]["rebalance_priority"]

    def test_demo_customers_without_p013(self):
        """C001、C002 未持仓活钱存款，用于验证展示层新开仓。"""
        for cid in ("C20250602001", "C20250602002", "C20250602007"):
            holdings = get_customer_holdings(cid)["holdings"]
            assert holdings.get(DEMAND_DEPOSIT_CODE, 0) < 0.01

    def test_demo_customers_with_p013(self):
        for cid in (
            "C20250602003",
            "C20250602004",
            "C20250602005",
            "C20250602006",
            "C20250602008",
        ):
            holdings = get_customer_holdings(cid)["holdings"]
            assert holdings.get(DEMAND_DEPOSIT_CODE, 0) > 0.01

    def test_engine_routes_cash_buy_to_p013_when_held(self):
        """已持仓 P000 时，底层 consolidate 优先 P000（无需展示层改写）。"""
        cid = "C20250602003"
        data = get_customer_holdings(cid)
        customer = get_demo_customer(cid)
        engine = AutoRebalanceEngine()
        engine.solver["consolidate_category_rebalance"] = True
        result = engine.rebalance(
            customer_id=cid,
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        spend_buys = [
            d
            for d in result.product_deltas
            if d.category == "spend" and d.action == "buy" and d.delta_amount > 0.01
        ]
        if spend_buys:
            assert all(d.product_code == DEMAND_DEPOSIT_CODE for d in spend_buys)

    def test_display_opens_p013_for_zero_holding_customer(self):
        """未持仓 P000 时，展示层将活钱类买入合并为 P000 新开仓。"""
        cid = "C20250602001"
        data = get_customer_holdings(cid)
        customer = get_demo_customer(cid)
        engine = AutoRebalanceEngine()
        result = engine.rebalance(
            customer_id=cid,
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=FOUR_MONEY_PLANNING,
        )
        raw_buys = [
            d
            for d in result.product_deltas
            if d.category == "spend"
            and d.action == "buy"
            and d.delta_amount > 0.01
        ]
        assert raw_buys
        assert any(d.product_code != DEMAND_DEPOSIT_CODE for d in raw_buys)

        displayed = apply_demand_deposit_display(
            result.product_deltas, data["holdings"]
        )
        spend_buys = [
            d
            for d in displayed
            if d.category == "spend"
            and d.action == "buy"
            and d.delta_amount > 0.01
        ]
        assert len(spend_buys) == 1
        assert spend_buys[0].product_code == DEMAND_DEPOSIT_CODE
        assert spend_buys[0].current_amount < 0.01
        assert spend_buys[0].delta_amount == pytest.approx(
            sum(d.delta_amount for d in raw_buys), abs=0.02
        )

    def test_display_same_rule_for_investment_planning(self):
        """投资规划 cash 类与综合规划 spend 类同一展示规则。"""
        cid = "C20250602002"
        data = get_customer_holdings(cid)
        customer = get_demo_customer(cid)
        engine = AutoRebalanceEngine()
        result = engine.rebalance(
            customer_id=cid,
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            product_category=INVESTMENT_PLANNING,
        )
        apply_demand_deposit_to_result(result, data["holdings"])
        cash_buys = [
            d
            for d in result.product_deltas
            if d.category == "cash"
            and d.action == "buy"
            and d.delta_amount > 0.01
        ]
        if cash_buys:
            assert all(d.product_code == DEMAND_DEPOSIT_CODE for d in cash_buys)
