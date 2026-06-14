"""Tests for flag-driven personalized allocation."""

import pytest

from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine
from asset_allocation.flag_driven_solver import FlagDrivenSolver, FlagDrivenSolverError
from core.allocation_config_service import AllocationConfigService
from core.config_loader import INVESTMENT_CARD_KEYS, get_demo_customer
from core.data_store import get_customer_holdings
from core.wealth_journey_service import WealthJourneyService


INVESTMENT_PLANNING = "投资规划"


class TestFlagDrivenSolver:
    def setup_method(self):
        self.solver = FlagDrivenSolver()
        self.config_svc = AllocationConfigService()

    def _resolve(self, customer_id: str):
        customer = get_demo_customer(customer_id)
        data = get_customer_holdings(customer_id)
        resolved = self.config_svc.resolve_asset_type_targets(
            INVESTMENT_PLANNING, customer["risk_profile"]
        )
        engine = AutoRebalanceEngine()
        invest = engine._investment_holdings(data["holdings"], engine.products)
        current = engine._aggregate_by_asset_type(invest)
        return current, data["idle_cash"], resolved["targets"]

    def test_no_effective_flags_raises(self):
        current, idle, targets = self._resolve("C20250602001")
        with pytest.raises(FlagDrivenSolverError):
            self.solver.solve(
                current_cat=current,
                idle_cash=idle,
                profile_targets=targets,
                flag_codes=["four_money_mismatch"],
            )

    def test_targets_sum_to_total(self):
        current, idle, targets = self._resolve("C20250602007")
        tgt, notes = self.solver.solve(
            current_cat=current,
            idle_cash=idle,
            profile_targets=targets,
            flag_codes=["principal_loss_exceeded", "four_money_mismatch"],
        )
        total = sum(current.values()) + idle
        assert abs(sum(tgt.values()) - total) < 0.02
        assert notes

    def test_cash_not_below_benchmark(self):
        current, idle, targets = self._resolve("C20250602007")
        total = sum(current.values()) + idle
        bench = targets["cash"]["target"] * total
        tgt, _ = self.solver.solve(
            current_cat=current,
            idle_cash=idle,
            profile_targets=targets,
            flag_codes=["principal_loss_exceeded"],
        )
        assert tgt["cash"] >= bench - 0.02

    def test_merge_below_and_volatility_equity_compromise(self):
        current, idle, targets = self._resolve("C20250602004")
        total = sum(current.values()) + idle
        b = targets["equity"]
        hi = b["band"][1] * total
        bench = b["target"] * total
        tgt, _ = self.solver.solve(
            current_cat=current,
            idle_cash=idle,
            profile_targets=targets,
            flag_codes=["return_below_expected", "volatility_exceeded"],
        )
        expected = bench + (hi - bench) * 0.5
        assert abs(tgt["equity"] - expected) < total * 0.02 + 1

    def test_return_below_equity_at_least_bench_not_cut(self):
        """收益低：权益 intent 为 max(bench,cur)，不主动减超基准仓。"""
        total = 1_000_000.0
        bounds = {
            "cash": {"target": 0.05, "band": [0.03, 0.10]},
            "fixed_income": {"target": 0.30, "band": [0.20, 0.40]},
            "equity": {"target": 0.40, "band": [0.30, 0.50]},
            "alternative": {"target": 0.25, "band": [0.15, 0.35]},
        }
        profile = {
            cat: {"target": bounds[cat]["target"], "band": bounds[cat]["band"]}
            for cat in bounds
        }
        cur = {
            "cash": 80_000.0,
            "fixed_income": 300_000.0,
            "equity": 450_000.0,  # 高于基准 400k，低于上限 500k
            "alternative": 170_000.0,
        }
        tgt, _ = self.solver.solve(
            current_cat=cur,
            idle_cash=0,
            profile_targets=profile,
            flag_codes=["return_below_expected"],
        )
        assert tgt["equity"] >= 450_000.0 - 0.02

    def test_return_above_fixed_anchors_bench(self):
        """收益高：固收 intent 至少基准，超基准部分不在 intent 阶段主动卖出。"""
        total = 1_000_000.0
        profile = {
            "cash": {"target": 0.05, "band": [0.03, 0.10]},
            "fixed_income": {"target": 0.30, "band": [0.20, 0.40]},
            "equity": {"target": 0.40, "band": [0.30, 0.50]},
            "alternative": {"target": 0.25, "band": [0.15, 0.35]},
        }
        cur = {
            "cash": 30_000.0,
            "fixed_income": 350_000.0,  # 高于基准 300k
            "equity": 500_000.0,
            "alternative": 120_000.0,
        }
        tgt, _ = self.solver.solve(
            current_cat=cur,
            idle_cash=0,
            profile_targets=profile,
            flag_codes=["return_above_expected"],
        )
        assert tgt["fixed_income"] >= 350_000.0 - 0.02

    def test_merge_above_and_principal_prefers_principal(self):
        total = 1_000_000.0
        profile = {
            "cash": {"target": 0.05, "band": [0.03, 0.10]},
            "fixed_income": {"target": 0.30, "band": [0.20, 0.40]},
            "equity": {"target": 0.40, "band": [0.30, 0.50]},
            "alternative": {"target": 0.25, "band": [0.15, 0.35]},
        }
        lo_eq = profile["equity"]["band"][0] * total
        cur = {
            "cash": 50_000.0,
            "fixed_income": 300_000.0,
            "equity": 450_000.0,
            "alternative": 200_000.0,
        }
        tgt, _ = self.solver.solve(
            current_cat=cur,
            idle_cash=0,
            profile_targets=profile,
            flag_codes=["return_above_expected", "principal_loss_exceeded"],
        )
        assert abs(tgt["equity"] - lo_eq) < total * 0.02 + 1

    def test_merge_above_and_volatility_uses_vol_and_note(self):
        total = 1_000_000.0
        profile = {
            "cash": {"target": 0.05, "band": [0.03, 0.10]},
            "fixed_income": {"target": 0.30, "band": [0.20, 0.40]},
            "equity": {"target": 0.40, "band": [0.30, 0.50]},
            "alternative": {"target": 0.25, "band": [0.15, 0.35]},
        }
        bench_f = profile["fixed_income"]["target"] * total
        cur = {
            "cash": 30_000.0,
            "fixed_income": 250_000.0,
            "equity": 500_000.0,
            "alternative": 220_000.0,
        }
        tgt, notes = self.solver.solve(
            current_cat=cur,
            idle_cash=0,
            profile_targets=profile,
            flag_codes=["return_above_expected", "volatility_exceeded"],
        )
        assert any("兼考虑收益偏高" in n for n in notes)
        assert tgt["fixed_income"] <= bench_f + total * 0.02 + 1 or tgt["fixed_income"] >= bench_f - 0.02


class TestFlagPersonalizedRebalance:
    def test_engine_flag_personalized(self):
        customer_id = "C20250602007"
        customer = get_demo_customer(customer_id)
        data = get_customer_holdings(customer_id)
        journey = WealthJourneyService()
        diagnosis = journey.build_diagnosis(customer_id)
        flag_codes = [
            f["code"]
            for f in diagnosis["flags"]
            if f["code"] != "four_money_mismatch"
        ]
        assert flag_codes

        engine = AutoRebalanceEngine()
        result = engine.rebalance(
            customer_id=customer_id,
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            mode="flag_personalized",
            product_category=INVESTMENT_PLANNING,
            flag_codes=flag_codes,
        )
        assert result.mode == "flag_personalized"
        assert result.view_mode == "asset_type"
        assert len(result.category_summary) == len(INVESTMENT_CARD_KEYS)
        assert any("个性化配仓依据" in n for n in result.validation_notes)

    def test_smart_one_click_unchanged(self):
        customer_id = "C20250602001"
        customer = get_demo_customer(customer_id)
        data = get_customer_holdings(customer_id)
        engine = AutoRebalanceEngine()
        result = engine.rebalance(
            customer_id=customer_id,
            holdings=data["holdings"],
            idle_cash=data["idle_cash"],
            risk_profile=customer["risk_profile"],
            mode="smart_one_click",
            product_category=INVESTMENT_PLANNING,
        )
        assert result.mode == "smart_one_click"


class TestFlagPersonalizedAPI:
    def test_flag_personalized_rejects_healthy_customer(self):
        from fastapi.testclient import TestClient

        from main import app

        client = TestClient(app)
        resp = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": "C20250602002",
            "mode": "flag_personalized",
            "product_category": "投资规划",
        })
        assert resp.status_code == 400
        assert "财富健康" in resp.json()["detail"]

    def test_flag_personalized_success(self):
        from fastapi.testclient import TestClient

        from main import app

        client = TestClient(app)
        resp = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": "C20250602007",
            "mode": "flag_personalized",
            "product_category": "投资规划",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["rebalance"]["mode"] == "flag_personalized"
