"""API integration tests."""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
CUSTOMER_ID = "C20250602001"


class TestAssetOverviewAPI:
    def test_overview_success(self):
        resp = client.get(f"/api/asset/overview?customer_id={CUSTOMER_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["customer_id"] == CUSTOMER_ID
        assert len(data["data"]["categories"]) == 4

    def test_overview_not_found(self):
        resp = client.get("/api/asset/overview?customer_id=INVALID")
        assert resp.status_code == 404

    def test_overview_comprehensive_planning(self):
        resp = client.get(
            f"/api/asset/overview?customer_id={CUSTOMER_ID}&product_category=综合规划"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["product_category"] == "综合规划"
        assert data["allocation_mapping"]["model_code"] == "综合规划P3"


class TestAutoRebalanceAPI:
    def test_full_rebalance(self):
        resp = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": CUSTOMER_ID,
            "mode": "smart_one_click",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "rebalance" in data
        assert "explanation" in data
        assert len(data["rebalance"]["category_summary"]) == 4

    def test_single_category(self):
        resp = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": CUSTOMER_ID,
            "target_category": "preserve",
        })
        assert resp.status_code == 200

    def test_manual_tweak(self):
        resp = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": CUSTOMER_ID,
            "mode": "manual_tweak",
            "manual_overrides": {"spend": 100000},
            "locked_categories": ["spend"],
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["rebalance"]["mode"] == "manual_tweak"


class TestPageConstraintsAPI:
    def test_page_constraints_default_off(self):
        resp = client.get("/api/allocation/page_constraints")
        assert resp.status_code == 200
        assert resp.json()["data"]["product_limit_validation_enabled"] is False


class TestProductCandidatesAPI:
    def test_list_candidates(self):
        resp = client.get("/api/products/candidates?category=preserve")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["category"] == "preserve"
        codes = {p["code"] for p in data["products"]}
        assert "P004" in codes
        assert "P005" in codes

    def test_list_candidates_by_asset_type(self):
        resp = client.get("/api/products/candidates?category=fixed_income")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["category"] == "fixed_income"
        assert data["products"]
        assert all(p["category"] == "fixed_income" for p in data["products"])
        codes = {p["code"] for p in data["products"]}
        assert "P004" in codes
        assert "P005" in codes


class TestManualAdjustAPI:
    def test_manual_adjust(self):
        base = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": CUSTOMER_ID,
            "mode": "smart_one_click",
        }).json()["data"]["rebalance"]
        baseline = {d["product_code"]: d["target_amount"] for d in base["product_deltas"]}
        first = next(iter(baseline))
        new_target = baseline[first] + 30000

        resp = client.post("/api/allocation/manual_adjust", json={
            "customer_id": CUSTOMER_ID,
            "product_targets": {first: new_target},
            "baseline_product_targets": baseline,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["rebalance"]["mode"] == "manual_product_edit"
        assert len(data["rebalance"]["category_summary"]) == 4
        assert "explanation" in data

    def test_manual_adjust_new_zero_holding(self):
        base = client.post("/api/allocation/auto_rebalance", json={
            "customer_id": CUSTOMER_ID,
            "mode": "smart_one_click",
        }).json()["data"]["rebalance"]
        baseline = {d["product_code"]: d["target_amount"] for d in base["product_deltas"]}
        baseline["P011"] = 0.0
        resp = client.post("/api/allocation/manual_adjust", json={
            "customer_id": CUSTOMER_ID,
            "product_targets": {"P011": 50000},
            "baseline_product_targets": baseline,
        })
        assert resp.status_code == 200
        deltas = resp.json()["data"]["rebalance"]["product_deltas"]
        p011 = next(d for d in deltas if d["product_code"] == "P011")
        assert p011["current_amount"] == 0.0
        assert p011["target_amount"] == 50000.0
        assert p011["action"] == "buy"


class TestHealth:
    def test_health_check(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
