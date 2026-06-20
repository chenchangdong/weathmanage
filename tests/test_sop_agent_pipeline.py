"""SOP 6.2 管道与配置测试。"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.sop_agent_pipeline import SopAgentPipeline
from core.sop_script_builder import SopScriptBuilder
from core.sop_product_info_service import SopProductInfoService
from main import app

client = TestClient(app)


@pytest.fixture
def sample_event() -> dict:
    return {
        "event_id": "EVT99",
        "scenario": "最大回撤超阈值",
        "composite_code": "EVT_DRAWDOWN",
        "product_code": "A108",
        "product_name": "test-磐石3.0-A108",
        "category": "low",
        "category_label": "稳健型",
        "asset_type": "fixed_income",
        "asset_type_label": "固收类",
        "strategy_type": "",
        "drawdown_detail": "近60日最大回撤达 -6.29%，超阈值 -5%",
        "rule_hits": ["RISK_MAX_DD_5"],
        "data_date": "2026-06-02",
        "level": "高",
    }


@pytest.fixture
def sample_yield_event() -> dict:
    return {
        "event_id": "EVT100",
        "scenario": "收益不达预期",
        "composite_code": "EVT_YIELD",
        "product_code": "prd-ms-B5",
        "product_name": "磐石3.0（演示产品）",
        "category": "mod",
        "category_label": "平衡型",
        "asset_type": "fixed_income",
        "asset_type_label": "固收类",
        "strategy_type": "",
        "drawdown_detail": "近60日收益率 1.21%，低于阈值 2%",
        "rule_hits": ["YIELD_LOW_2"],
        "data_date": "2026-06-19",
        "level": "中",
    }


class TestSopAgentPipeline:
    def test_pipeline_four_steps(self, sample_event):
        out = SopAgentPipeline().run(sample_event)
        assert out["pipeline_version"] == "1.0"
        assert "621_event_description" in out["steps"]
        assert "622_product_info" in out["steps"]
        assert "623_research_analysis" in out["steps"]
        assert "624_client_script" in out["steps"]
        assert "售后提醒" in out["event_description"]
        assert out["product_info"]["static"]["product_id"] == "A108"
        assert out["research_analysis"].get("framework")
        assert len(out["client_script"]) >= 50

    def test_yield_pipeline_uses_yield_wording(self, sample_yield_event):
        out = SopAgentPipeline().run(sample_yield_event, use_llm=False)
        script = out["client_script"]
        research = out["research_analysis"]
        assert "收益率" in script
        assert "回撤约" not in script
        assert "收益" in research.get("structured", {}).get("phenomenon", "")
        assert "回撤是否源于选股" not in research.get("product_analysis", "")
        assert out["research_analysis"].get("framework") == "固收（纯债/债券型）"
        assert "近60日收益率" in out["event_description"]
        assert "单日最大回撤" not in out["event_description"]
        assert "建议与客户" not in script
        assert "与客户沟通" not in script
        assert "您" in script

    def test_product_info_degraded(self):
        pkg = SopProductInfoService().fetch_info_package("A108", "2026-06-02")
        assert "evaluation_db" in pkg["degraded"]
        assert "product_reports" in pkg["degraded"]
        assert pkg["static"]["product_name"]
        assert pkg["static"]["category_label"] == "稳健型"
        assert pkg["static"]["asset_type"] == "fixed_income"

    def test_banned_words_sanitize(self):
        raw = "市场出现暴跌，保证收益不受影响"
        text, warnings = SopScriptBuilder().sanitize(raw)
        assert "暴跌" not in text
        assert "保证收益" not in text
        assert len(warnings) >= 1


class TestSopAgentAPI:
    def test_agent_config(self):
        resp = client.get("/api/sop/agent/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["batch_schedule"]["hour"] == 20

    def test_schedule_status(self):
        resp = client.get("/api/sop/agent/schedule/status")
        assert resp.status_code == 200
        assert "enabled" in resp.json()["data"]

    def test_run_pipeline_via_api(self):
        batch = client.post("/api/sop/events/run-batch", json={"as_of": "2026-06-02"})
        assert batch.status_code == 200
        events = batch.json()["data"].get("events") or []
        if not events:
            pytest.skip("no composite events from batch")
        eid = events[0]["event_id"]
        run = client.post("/api/sop/agent/run", json={"event_id": eid})
        assert run.status_code == 200
        out = run.json()["data"]
        assert out["steps"]["621_event_description"]["step"] == "6.2.1"
        assert out["steps"]["624_client_script"]["step"] == "6.2.4"
