"""资产配置模型与五档风险映射测试."""

import pytest

from core.allocation_config_service import AllocationConfigService
from core.config_loader import load_model_config, load_portfolio_mapping


def _mapped_model(risk: str) -> str:
    pm = load_portfolio_mapping()["portfolio_map"]["投资规划"]
    defaults = load_portfolio_mapping()["risk_loss_default"]["投资规划"]
    loss_key = defaults[risk]
    return pm[loss_key]["target_model"]


class TestFiveRiskLevels:
    def setup_method(self):
        self.svc = AllocationConfigService()

    def test_ten_models_two_categories(self):
        models = list(load_model_config()["model_list"].keys())
        assert len(models) == 10
        pm = load_portfolio_mapping()["portfolio_map"]
        for cat in ("投资规划", "综合规划"):
            targets = {e["target_model"] for e in pm[cat].values()}
            assert targets.issubset(set(models))
            assert len(targets) == 5

    def test_portfolio_map_categories(self):
        pm = load_portfolio_mapping()
        assert "综合规划" in pm.get("portfolio_map", {})
        assert "投资规划" in pm["portfolio_map"]

    def test_loss_key_mapping(self):
        assert self.svc.get_loss_key_for_risk("投资规划", "conservative") == "loss_1pct"
        assert self.svc.get_loss_key_for_risk("投资规划", "prudent") == "loss_3pct"
        assert self.svc.get_loss_key_for_risk("投资规划", "balanced") == "loss_6pct"
        assert self.svc.get_loss_key_for_risk("投资规划", "growth") == "loss_10pct"
        assert self.svc.get_loss_key_for_risk("投资规划", "aggressive") == "loss_15pct"

    def test_get_model_balanced(self):
        m = self.svc.get_model_by_customer_risk("投资规划", "balanced")
        assert m["loss_key"] == "loss_6pct"
        assert m["model_code"] == _mapped_model("balanced")

    def test_get_model_prudent(self):
        m = self.svc.get_model_by_customer_risk("投资规划", "prudent")
        assert m["model_code"] == _mapped_model("prudent")

    def test_get_model_growth(self):
        m = self.svc.get_model_by_customer_risk("投资规划", "growth")
        assert m["model_code"] == _mapped_model("growth")

    def test_calc_four_money_threshold_p1(self):
        limits = load_model_config()["model_list"]["投资规划P1"]["asset_limit"]
        th = self.svc.calc_four_money_threshold("投资规划P1")
        spend = th["thresholds"]["spend"]
        assert spend["lower_pct"] == limits["cash"][0]
        assert spend["benchmark_pct"] == limits["cash"][1]
        assert spend["upper_pct"] == limits["cash"][2]
        grow = th["thresholds"]["grow"]
        assert grow["benchmark_pct"] == limits["equity"][1] + limits["alternative"][1]

    def test_calc_four_money_threshold_has_grow_cap(self):
        """生钱的钱上限 = 权益上限 + 另类基准，封顶 100%。"""
        code = _mapped_model("balanced")
        th = self.svc.calc_four_money_threshold(code)
        grow = th["thresholds"]["grow"]
        assert grow["upper_pct"] <= 100.0
        assert grow["benchmark_pct"] >= grow["lower_pct"]

    def test_resolve_conservative_uses_p1(self):
        data = self.svc.resolve_profile_targets("投资规划", "conservative")
        assert data["model"]["model_code"] == _mapped_model("conservative")

    def test_four_money_benchmark_sum_p1(self):
        model = load_model_config()["model_list"]["投资规划P1"]
        total = self.svc.calc_four_money_benchmark_sum(model["asset_limit"])
        assert total == pytest.approx(100.0)

    def test_comprehensive_planning_benchmark_sum(self):
        for code in ("综合规划P1", "综合规划P2", "综合规划P3", "综合规划P4", "综合规划P5"):
            limits = load_model_config()["model_list"][code]["asset_limit"]
            total = self.svc.calc_four_money_benchmark_sum(limits)
            assert total == pytest.approx(100.0)

    def test_validate_benchmark_sum_rejects_invalid(self):
        limits = {
            "cash": [10, 20, 25],
            "fixed_income": [10, 25, 30],
            "equity": [10, 20, 35],
            "alternative": [0, 10, 20],
            "insurance": [0, 5, 10],
        }
        with pytest.raises(ValueError, match="100%"):
            self.svc.validate_four_money_benchmark_sum(limits, model_label="TEST")


class TestModelConfigAPI:
    def test_list_models(self, client):
        resp = client.get("/api/model/list")
        assert resp.status_code == 200
        models = resp.json()["data"]["models"]
        assert len(models) == 10
        first = models[0]
        assert "asset_limit" in first
        assert "cash" in first["asset_limit"]
        assert len(first["asset_limit"]["cash"]) == 3

    def test_risk_levels(self, client):
        resp = client.get("/api/risk/levels")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["levels"]) == 5

    def test_resolve_balanced(self, client):
        resp = client.get(
            "/api/allocation/resolve?product_category=投资规划&risk_label=balanced"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["model"]["model_code"] == _mapped_model("balanced")

    def test_portfolio_map_has_5_rows(self, client):
        resp = client.get("/api/portfolio/map")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["rows"]) == 10

    def test_overview_includes_mapping(self, client):
        resp = client.get(
            "/api/asset/overview?customer_id=C20250602001&product_category=投资规划"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["allocation_mapping"]["model_code"] == _mapped_model("balanced")
        assert data["product_category"] == "投资规划"

    def test_overview_comprehensive_model(self, client):
        resp = client.get(
            "/api/asset/overview?customer_id=C20250602001&product_category=综合规划"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["allocation_mapping"]["model_code"] == "综合规划P3"
        assert data["product_category"] == "综合规划"
        assert data["view_mode"] == "four_money"
        assert len(data["categories"]) == 4
        assert data["categories"][0]["category"] in ("spend", "preserve", "grow", "protect")

    def test_overview_investment_asset_type_cards(self, client):
        resp = client.get(
            "/api/asset/overview?customer_id=C20250602001&product_category=投资规划"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["view_mode"] == "asset_type"
        cats = {c["category"] for c in data["categories"]}
        assert cats == {"cash", "fixed_income", "equity", "alternative"}
        assert data["excluded_insurance_amount"] == 32000.0
        assert data["total_assets"] == 1012000.0 - 32000.0

    def test_investment_rebalance_no_insurance_trades(self, client):
        resp = client.post(
            "/api/allocation/auto_rebalance",
            json={
                "customer_id": "C20250602001",
                "product_category": "投资规划",
                "mode": "smart_one_click",
            },
        )
        assert resp.status_code == 200
        rb = resp.json()["data"]["rebalance"]
        assert rb["view_mode"] == "asset_type"
        codes = {d["product_code"] for d in rb["product_deltas"] if abs(d["delta_amount"]) >= 1}
        assert "P009" not in codes
        assert "P010" not in codes
        summary_cats = {s["category"] for s in rb["category_summary"]}
        assert summary_cats == {"cash", "fixed_income", "equity", "alternative"}

    def test_model_delete_check_mapped(self, client):
        code = _mapped_model("balanced")
        resp = client.get(f"/api/model/delete-check?model_code={code}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["deletable"] is False
        assert len(data["mapping_refs"]) >= 1

    def test_model_delete_blocked_when_mapped(self, client):
        code = _mapped_model("balanced")
        resp = client.post("/api/model/delete", json={"model_code": code})
        assert resp.status_code == 400
        assert "风险映射" in resp.json()["detail"]

    def test_model_save_rejects_benchmark_sum_not_100(self, client):
        list_resp = client.get("/api/model/list")
        models = list_resp.json()["data"]["models"]
        model_list = {}
        for m in models:
            detail = client.get(f"/api/model/detail?model_code={m['model_code']}").json()["data"]
            model_list[m["model_code"]] = {
                "model_name": detail["model_name"],
                "expect_annual_return": detail["expect_annual_return"],
                "expect_volatility": detail["expect_volatility"],
                "asset_limit": detail["asset_limit"],
            }
        first = models[0]["model_code"]
        model_list[first]["asset_limit"]["cash"] = [10, 10, 25]
        resp = client.post("/api/model/save", json={"model_list": model_list})
        assert resp.status_code == 400
        assert "100%" in resp.json()["detail"]
