"""AI advisor chat API tests."""

import pytest

CUSTOMER_ID = "C20250602001"


class TestAIChatAPI:
    def test_ai_status(self, client):
        resp = client.get("/api/ai/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "configured" in data
        assert "model" in data

    def test_chat_empty_message(self, client):
        resp = client.post("/api/ai/chat", json={
            "customer_id": CUSTOMER_ID,
            "message": "   ",
        })
        assert resp.status_code == 400

    def test_chat_fallback_without_api_key(self, client, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        resp = client.post("/api/ai/chat", json={
            "customer_id": CUSTOMER_ID,
            "message": "请解读该客户财富健康度",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source"] == "fallback"
        assert "张女士" in data["reply"] or CUSTOMER_ID in str(data.get("grounding_summary", {}))

    def test_chat_with_overview_context(self, client, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        ov = client.get(f"/api/asset/overview?customer_id={CUSTOMER_ID}").json()["data"]
        resp = client.post("/api/ai/chat", json={
            "customer_id": CUSTOMER_ID,
            "message": "哪些大类超出模型区间？",
            "overview": ov,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["grounding_summary"]["has_overview"] is True


class TestAdvisorChatService:
    def test_build_grounding(self):
        from agent_core.chat_context import build_chat_grounding

        g = build_chat_grounding(CUSTOMER_ID)
        assert g["customer"]["name"]
        assert g["asset_overview"]["available"] is True

    def test_status(self):
        from agent_core.advisor_chat import AdvisorChatService

        st = AdvisorChatService().status()
        assert "configured" in st

    def test_chat_returns_reasoning_when_llm_provides_it(self, monkeypatch):
        from agent_core.advisor_chat import AdvisorChatService

        def fake_chat(self, messages, **kwargs):
            return {
                "content": "最终回复正文",
                "reasoning": "第一步分析持仓\n第二步对照模型区间",
                "model": "test-model",
                "usage": {},
            }

        monkeypatch.setattr(
            "agent_core.advisor_chat.LLMClient.chat",
            fake_chat,
        )
        monkeypatch.setattr(
            "agent_core.advisor_chat.LLMClient.is_configured",
            lambda self: True,
        )

        result = AdvisorChatService().chat(
            customer_id=CUSTOMER_ID,
            message="请解读配置方案",
        )
        assert result["source"] == "llm"
        assert result["reply"].startswith("最终回复正文")
        assert "第一步分析持仓" in result["reasoning"]
