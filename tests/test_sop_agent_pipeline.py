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
        "strategy_type": "多策略",
        "drawdown_detail": "近60日最大回撤达 -6.29%，超阈值 -5%",
        "rule_hits": ["RISK_MAX_DD_5"],
        "data_date": "2026-06-02",
        "level": "高",
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

    def test_product_info_degraded(self):
        pkg = SopProductInfoService().fetch_info_package("A108", "2026-06-02")
        assert "evaluation_db" in pkg["degraded"]
        assert "product_reports" in pkg["degraded"]
        assert pkg["static"]["product_name"]

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
        assert data["batch_schedule"]["hour"] == 21

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
