"""SOP 6.2.5 飞书推送 — 受众解析与卡片组装。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.sop_audience_resolver import resolve_event_audiences
from core.sop_feishu_card_builder import build_push_card
from core.sop_push_service import SopPushService


class TestSopAudienceResolver:
    def test_prd_ms_b5_holders(self):
        audiences = resolve_event_audiences("prd-ms-B5")
        ids = {a["customer_id"] for a in audiences}
        assert "C20250602004" in ids
        assert all(a["advisor_id"] == "RM_CCD" for a in audiences)
        assert all(a["advisor_name"] == "陈长东" for a in audiences)

    def test_t305_holder_li(self):
        audiences = resolve_event_audiences("T305")
        assert len(audiences) == 1
        assert audiences[0]["customer_name"] == "李先生"


class TestSopFeishuCard:
    def test_build_card_contains_customer(self):
        event = {
            "event_id": "EVT01",
            "scenario": "最大回撤异常",
            "product_name": "测试产品",
            "product_code": "T305",
            "data_date": "2026-06-19",
            "level": "高",
            "drawdown_detail": "最大回撤 4.9%",
        }
        output = {
            "event_description": "【2026-06-19 售后提醒】测试",
            "client_script": "尊敬的客户您好，请关注产品表现。",
            "research_analysis": {
                "structured": {
                    "phenomenon": "回撤偏大",
                    "cause": "市场波动",
                    "outlook": "建议持有观察",
                }
            },
        }
        aud = {
            "customer_name": "李先生",
            "risk_profile_name": "保守型",
            "holding_amount": 50000,
        }
        card = build_push_card(event=event, output=output, audience=aud)
        body = str(card)
        assert "李先生" in body
        assert "对客话术" in body


class TestSopPushService:
    def test_push_event_no_holders(self):
        store = MagicMock()
        store.get_composite_event.return_value = {
            "event_id": "EVTX",
            "product_code": "NONEXIST",
            "agent_status": "done",
        }
        store.get_agent_output.return_value = {"agent_status": "done", "client_script": "hi"}
        svc = SopPushService(store=store)
        with patch.object(svc, "_maybe_sync_advisors_before_push"):
            result = svc.push_event("EVTX")
        assert result["skipped_no_holders"] is True
        store.save_push_result.assert_called_once()

    @patch("core.sop_push_service.get_advisor_record")
    @patch("core.sop_push_service.FeishuClient")
    def test_push_event_sends_per_customer(self, mock_client_cls, mock_get_advisor):
        mock_client = mock_client_cls.return_value
        mock_client.resolve_open_id.return_value = "ou_test"
        mock_client.send_interactive_card.return_value = "msg_1"
        mock_get_advisor.return_value = {
            "id": "RM_CCD",
            "name": "陈长东",
            "feishu_open_id": "ou_test",
        }

        store = MagicMock()
        store.get_composite_event.return_value = {
            "event_id": "EVT02",
            "product_code": "T305",
            "product_name": "test-顶点-灵活T3",
            "scenario": "回撤",
            "data_date": "2026-06-19",
            "agent_status": "done",
        }
        store.get_agent_output.return_value = {
            "agent_status": "done",
            "event_description": "提醒",
            "client_script": "话术",
            "research_analysis": {},
        }

        svc = SopPushService(store=store)
        with patch.object(svc, "_maybe_sync_advisors_before_push"):
            with patch.dict(
                "os.environ",
                {"FEISHU_APP_ID": "cli_test", "FEISHU_APP_SECRET": "sec_test"},
            ):
                result = svc.push_event("EVT02")

        assert result["sent"] == 1
        assert result["failed"] == 0
        assert mock_client.send_interactive_card.call_count == 1
