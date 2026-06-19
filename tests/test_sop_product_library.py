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
        from core.config_loader import get_product_map, load_product_library
        from core.product_library_utils import is_allocation_product, is_sop_product

        lib = load_product_library()
        alloc = {
            p["product_id"]
            for p in lib.get("products") or []
            if is_allocation_product(p)
        }
        sop = {
            p["product_id"]
            for p in lib.get("products") or []
            if is_sop_product(p)
        }
        pmap = get_product_map()
        assert "A108" in sop
        assert "C201" in pmap  # SOP + asset_type → 资配候选
        assert "001" in pmap
        assert "000" in alloc
        assert "001" not in sop or "001" in alloc  # 资配 001 非 SOP
        assert "P001" in sop
        # 跑批 map 不含纯资配数字码
        batch_map = SopProductLibraryService().get_product_map()
        assert "001" not in batch_map
        assert "A108" in batch_map


class TestSopProductLibraryAPI:
    def test_config(self):
        resp = client.get("/api/sop/product-library/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "category_options" in body["data"]
        assert "asset_type_options" in body["data"]
        assert len(body["data"].get("products") or []) >= 1

    def test_product_asset_type(self):
        resp = client.get("/api/sop/info-products/C201")
        assert resp.status_code == 200
        row = resp.json()["data"]
        assert row.get("asset_type") == "equity"
        resp2 = client.get("/api/sop/info-products/prd-ms-B5")
        assert resp2.status_code == 200
        assert not resp2.json()["data"].get("asset_type")

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
