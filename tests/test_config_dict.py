"""可视化数据字典 API 测试。"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestConfigDictAPI:
    def test_tree(self):
        resp = client.get("/api/config-dict/tree")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 4
        assert data[0]["type"] == "group"

    def test_load_four_money_categories(self):
        resp = client.get("/api/config-dict/module/four_money_categories")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["view_type"] == "table"
        assert len(body["rows"]) == 4

    def test_unknown_module(self):
        resp = client.get("/api/config-dict/module/not_exists")
        assert resp.status_code == 404
