"""客户经理飞书 open_id 自动缓存与批量同步。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.advisor_feishu_cache import AdvisorFeishuCache, enrich_advisor_with_cache
from core.advisor_feishu_sync import AdvisorFeishuSyncService


class TestAdvisorFeishuCache:
    def test_set_and_get(self, tmp_path):
        cache = AdvisorFeishuCache(tmp_path / "cache.json")
        cache.set("RM001", feishu_open_id="ou_abc", source="test", advisor_name="张三")
        assert cache.get_open_id("RM001") == "ou_abc"

    def test_enrich_from_cache(self, tmp_path):
        cache = AdvisorFeishuCache(tmp_path / "cache.json")
        cache.set("RM_CCD", feishu_open_id="ou_cached", source="test")
        with patch("core.advisor_feishu_cache.AdvisorFeishuCache", return_value=cache):
            row = enrich_advisor_with_cache({"id": "RM_CCD", "name": "陈长东"})
        assert row["feishu_open_id"] == "ou_cached"


class TestAdvisorFeishuSync:
    @patch("core.advisor_feishu_sync.get_advisor_map")
    def test_sync_by_mobile_batch(self, mock_map, tmp_path):
        mock_map.return_value = {
            "RM001": {"id": "RM001", "name": "张三", "mobile": "13800000001"},
            "RM002": {"id": "RM002", "name": "李四", "mobile": "13800000002"},
        }
        client = MagicMock()
        client._timeout = 5.0
        client._headers.return_value = {"Authorization": "Bearer t"}

        svc = AdvisorFeishuSyncService(client)
        svc.cache = AdvisorFeishuCache(tmp_path / "cache.json")

        with patch.object(svc, "_batch_get_id", return_value={
            "13800000001": "ou_1",
            "13800000002": "ou_2",
        }):
            result = svc.sync_all(force=True)

        assert result["resolved"] == 2
        assert svc.cache.get_open_id("RM001") == "ou_1"
        assert svc.cache.get_open_id("RM002") == "ou_2"
