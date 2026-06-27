"""顾问 Agent Phase A — 工具与 API 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.advisor_agent import AdvisorAgentService
from agent_core.advisor_tools import execute_tool, tool_recommend_mode
from agent_core.journey_state import build_journey_context, infer_stage_from_page
from core.sop_event_store import SopEventStore

LI = "C20250602002"
CHEN = "C20250602005"
_FIXTURE_EVENTS = Path(__file__).resolve().parent / "fixtures" / "sop_events_demo.json"


@pytest.fixture
def sop_event_store(monkeypatch: pytest.MonkeyPatch) -> SopEventStore:
    store = SopEventStore(path=_FIXTURE_EVENTS)

    def _factory(path=None):
        return store if path is None else SopEventStore(path=path)

    for mod in (
        "core.sop_wealth_flags",
        "agent_core.advisor_tools",
        "core.sop_agent_service",
        "agent_core.advisor_nudge",
    ):
        monkeypatch.setattr(f"{mod}.SopEventStore", _factory)
    return store


class TestJourneyState:
    def test_infer_stage_from_page(self):
        assert infer_stage_from_page("asset_diagnosis.html") == "diagnosis"
        assert infer_stage_from_page("smart_allocation.html") == "allocation_work"

    def test_build_journey_with_diagnosis(self):
        from agent_core.advisor_tools import tool_get_diagnosis

        dx = tool_get_diagnosis(CHEN)
        ctx = build_journey_context(CHEN, diagnosis=dx["diagnosis"], page="asset_diagnosis.html")
        assert ctx["has_diagnosis"] is True
        assert ctx["stage"] == "diagnosis"


class TestAdvisorTools:
    def test_recommend_mode_for_li(self, sop_event_store: SopEventStore):
        rec = tool_recommend_mode(LI)
        assert rec["mode"] == "flag_personalized"
        assert rec["can_flag_personalized"] is True

    def test_recommend_mode_for_healthy_chen(self):
        rec = tool_recommend_mode(CHEN)
        assert rec["mode"] in ("optimal_personalized", "smart_one_click")

    def test_run_rebalance_smart_one_click(self):
        result = execute_tool("run_rebalance", CHEN, {"mode": "smart_one_click"})
        assert result["ok"] is True
        assert result["plan"]["rebalance"]["mode"] == "smart_one_click"


class TestAdvisorAgentAPI:
    def test_full_service_intent(self, client, sop_event_store: SopEventStore):
        resp = client.post("/api/ai/agent", json={
            "customer_id": LI,
            "message": "帮我完整服务李先生",
            "page": "wealth_inventory.html",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["intent"] == "full_service"
        assert data["customer_id"] == LI
        assert data["reply"]
        assert len(data["actions"]) >= 2
        assert any(a["type"] == "navigate" for a in data["actions"])
        assert any(a.get("tool") == "run_rebalance" for a in data["actions"])

    def test_diagnosis_intent(self, client, sop_event_store: SopEventStore):
        resp = client.post("/api/ai/agent", json={
            "customer_id": LI,
            "message": "解读一下诊断",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["intent"] == "diagnosis"
        assert "综合评分" in data["reply"]

    def test_tool_run_rebalance(self, client):
        resp = client.post("/api/ai/agent/tool", json={
            "customer_id": CHEN,
            "tool": "run_rebalance",
            "params": {"mode": "smart_one_click"},
        })
        assert resp.status_code == 200
        tr = resp.json()["data"]["tool_result"]
        assert tr["ok"] is True
        assert tr["plan"]["rebalance"]["customer_id"] == CHEN
        nav = next(a for a in resp.json()["data"]["actions"] if a.get("label") == "查看配仓方案")
        assert "plan" not in nav

    def test_execute_confirmed_tool_navigate_without_compact_plan(self):
        svc = AdvisorAgentService()
        out = svc.execute_confirmed_tool(CHEN, "run_rebalance", {"mode": "smart_one_click"})
        nav = next(a for a in out["actions"] if a.get("label") == "查看配仓方案")
        assert nav["href"] == "smart_allocation.html"
        assert "plan" not in nav

    def test_agent_service_turn(self, sop_event_store: SopEventStore):
        svc = AdvisorAgentService()
        out = svc.turn(LI, "帮我完整服务李先生", page="wealth_inventory.html")
        assert out["intent"] == "full_service"
        assert out["journey"]["customer_id"] == LI

    def test_full_service_current_customer(self, sop_event_store: SopEventStore):
        svc = AdvisorAgentService()
        out = svc.turn(CHEN, "帮我完整服务当前客户", page="wealth_inventory.html")
        assert out["intent"] == "full_service"
        assert out["journey"]["customer_id"] == CHEN

    def test_full_service_bare_prompt_uses_fallback(self, client, sop_event_store: SopEventStore):
        resp = client.post("/api/ai/agent", json={
            "customer_id": CHEN,
            "message": "帮我完整服务",
            "page": "wealth_inventory.html",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["customer_id"] == CHEN
