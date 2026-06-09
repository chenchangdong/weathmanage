"""AI product recommendation API tests."""

from core.product_recommend_service import ProductRecommendService, customer_risk_level_numeric

CUSTOMER_ID = "C20250602001"


class TestProductRecommendService:
    def test_customer_risk_numeric_mapping(self):
        assert customer_risk_level_numeric("conservative") == 1
        assert customer_risk_level_numeric("balanced") == 3
        assert customer_risk_level_numeric("aggressive") == 5

    def test_recommend_excludes_held_products(self):
        svc = ProductRecommendService()
        result = svc.recommend(CUSTOMER_ID, "fixed_income")
        codes = {p["code"] for p in result["products"]}
        assert "P003" not in codes
        assert "P004" not in codes
        assert result["customer_risk_level"] == 3

    def test_recommend_fixed_income_for_balanced(self):
        svc = ProductRecommendService()
        result = svc.recommend(CUSTOMER_ID, "fixed_income")
        assert len(result["products"]) == 1
        assert result["products"][0]["code"] == "P005"

    def test_recommend_alternative_for_balanced(self):
        svc = ProductRecommendService()
        result = svc.recommend(CUSTOMER_ID, "alternative")
        assert len(result["products"]) == 1
        assert result["products"][0]["code"] == "P011"
        assert result["products"][0]["risk_level"] == 3

    def test_recommend_respects_exclude_codes(self):
        svc = ProductRecommendService()
        result = svc.recommend(CUSTOMER_ID, "fixed_income", exclude_codes=["P005"])
        assert result["products"] == []

    def test_recommend_max_two(self):
        svc = ProductRecommendService()
        result = svc.recommend("C20250602002", "preserve", max_count=2)
        assert len(result["products"]) <= 2


class TestAIRecommendAPI:
    def test_ai_recommend_endpoint(self, client):
        resp = client.get(
            "/api/products/ai_recommend"
            f"?customer_id={CUSTOMER_ID}&category=fixed_income"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["customer_risk_level"] == 3
        assert len(data["products"]) == 1
        assert data["products"][0]["code"] == "P005"
        assert data["products"][0]["recommend_reason"]

    def test_ai_recommend_unknown_category(self, client):
        resp = client.get(
            f"/api/products/ai_recommend?customer_id={CUSTOMER_ID}&category=unknown_cat"
        )
        assert resp.status_code == 404
