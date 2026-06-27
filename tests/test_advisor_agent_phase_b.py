"""Phase B — 上下文预加载、Nudge、SOP 工具测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.advisor_nudge import build_proactive_nudge
from agent_core.advisor_tools import tool_generate_sop_content, tool_list_sop_events
from agent_core.context_preload import build_context_bundle, build_inventory_highlight
from core.sop_event_store import SopEventStore

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sop_events_demo.json"
LI = "C20250602002"


@pytest.fixture
def sop_event_store(monkeypatch: pytest.MonkeyPatch) -> SopEventStore:
    store = SopEventStore(path=_FIXTURE)

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


class TestContextPreload:
    def test_build_context_bundle(self, sop_event_store: SopEventStore):
        bundle = build_context_bundle(LI, page="asset_diagnosis.html")
        assert bundle["diagnosis"]["customer_id"] == LI
        assert bundle["journey"]["has_diagnosis"] is True
        assert "sop_compact" in bundle

    def test_inventory_highlight(self):
        h = build_inventory_highlight()
        assert h and h.get("customer_id")
        assert h.get("total_count", 0) >= 1


class TestSopTools:
    def test_list_sop_events_for_li(self, sop_event_store: SopEventStore):
        data = tool_list_sop_events(LI)
        assert data["ok"] is True
        assert len(data["events"]) >= 1
        assert data["events"][0]["product_code"] == "T305"

    def test_generate_sop_content_single(self, sop_event_store: SopEventStore):
        listed = tool_list_sop_events(LI)
        eid = listed["events"][0]["event_id"]
        out = tool_generate_sop_content(event_id=eid, use_llm=False)
        assert out["ok"] is True
        assert out["output"]["client_script"]


class TestProactiveNudge:
    def test_inventory_nudge(self):
        n = build_proactive_nudge("", page="wealth_inventory.html")
        assert n and n["id"] == "inventory_priority"
        assert any(a["type"] == "agent_prompt" for a in n["actions"])

    def test_sop_page_nudge(self):
        n = build_proactive_nudge("", page="sop_agent.html")
        assert n and n["id"] == "sop_console"

    def test_nudge_api(self, client, sop_event_store: SopEventStore):
        resp = client.get("/api/ai/nudge", params={"page": "wealth_inventory.html"})
        assert resp.status_code == 200
        assert resp.json()["data"]["nudge"]["id"] == "inventory_priority"

    def test_context_api(self, client, sop_event_store: SopEventStore):
        resp = client.get("/api/ai/context", params={
            "customer_id": LI,
            "page": "asset_diagnosis.html",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["diagnosis"]["customer_id"] == LI


class TestSopAgentIntent:
    def test_sop_intent(self, client, sop_event_store: SopEventStore):
        resp = client.post("/api/ai/agent", json={
            "customer_id": LI,
            "message": "该客户有哪些投后事件？",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["intent"] == "sop"
        assert "投后" in data["reply"] or "T305" in data["reply"] or "test" in data["reply"]

    def test_next_step_intent(self, client, sop_event_store: SopEventStore):
        resp = client.post("/api/ai/agent", json={
            "customer_id": LI,
            "message": "我接下来该做什么？",
            "page": "asset_diagnosis.html",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["intent"] == "next_step"
