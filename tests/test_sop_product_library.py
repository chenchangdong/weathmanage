"""SOP 产品信息库 API 测试（独立于资配 product_constraint）。"""

from fastapi.testclient import TestClient

from core.sop_product_library_service import SopProductLibraryService
from main import app

client = TestClient(app)


class TestSopProductLibraryService:
    def test_product_map_uses_sop_ids(self):
        pmap = SopProductLibraryService().get_product_map()
        assert "A108" in pmap
        assert pmap["A108"]["product_name"]
        assert pmap["A108"].get("manager_name")

    def test_independent_from_allocation_products(self):
        from core.config_loader import load_product_constraint, load_sop_product_library

        alloc = {p["code"] for p in load_product_constraint().get("products") or []}
        sop = {p["product_id"] for p in load_sop_product_library().get("products") or []}
        assert "A108" in sop
        assert load_sop_product_library()["page"]["title"] == "SOP产品信息库"
        # 两套产品库字段体系不同（code vs product_id），文件亦独立
        assert "P000" in alloc


class TestSopProductLibraryAPI:
    def test_config(self):
        resp = client.get("/api/sop/product-library/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "category_options" in body["data"]
        assert len(body["data"].get("products") or []) >= 1

    def test_list_products(self):
        resp = client.get("/api/sop/info-products/?page=1&page_size=5")
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["total"] >= 1
        assert len(payload["data"]) <= 5
        assert "product_id" in payload["data"][0]

    def test_get_product(self):
        resp = client.get("/api/sop/info-products/A108")
        assert resp.status_code == 200
        row = resp.json()["data"]
        assert row["product_id"] == "A108"

    def test_list_managers(self):
        resp = client.get("/api/sop/managers/list?page=1&page_size=10")
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["total"] >= 1
        assert "product_count" in payload["data"][0]
