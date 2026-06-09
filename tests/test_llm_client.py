"""LLM client response parsing tests."""

from agent_core.llm_client import LLMClient


class TestLLMClientParsing:
    def test_splits_content_and_reasoning(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def fake_post(self, url, json=None, headers=None):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "model": "qwen-test",
                        "choices": [{
                            "message": {
                                "content": "面向用户的答案",
                                "reasoning_content": "内部推理步骤",
                            },
                        }],
                        "usage": {"total_tokens": 10},
                    }

            return Resp()

        monkeypatch.setattr("httpx.Client.post", fake_post)
        monkeypatch.setattr("httpx.Client.__enter__", lambda self: self)
        monkeypatch.setattr("httpx.Client.__exit__", lambda *a: None)

        out = LLMClient().chat([{"role": "user", "content": "hi"}])
        assert out["content"] == "面向用户的答案"
        assert out["reasoning"] == "内部推理步骤"

    def test_reasoning_only_falls_back_to_content(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def fake_post(self, url, json=None, headers=None):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "choices": [{
                            "message": {
                                "content": "",
                                "reasoning_content": "仅有思考内容",
                            },
                        }],
                        "usage": {},
                    }

            return Resp()

        monkeypatch.setattr("httpx.Client.post", fake_post)
        monkeypatch.setattr("httpx.Client.__enter__", lambda self: self)
        monkeypatch.setattr("httpx.Client.__exit__", lambda *a: None)

        out = LLMClient().chat([{"role": "user", "content": "hi"}])
        assert out["content"] == "仅有思考内容"
        assert out["reasoning"] == ""

    def test_chat_stream_emits_reasoning_and_content(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        lines = [
            'data: {"choices":[{"delta":{"reasoning_content":"思考A"}}]}',
            'data: {"choices":[{"delta":{"content":"回答B"}}]}',
            "data: [DONE]",
        ]

        class FakeStreamResp:
            def __init__(self):
                self._idx = 0

            def raise_for_status(self):
                return None

            def iter_lines(self):
                for line in lines:
                    yield line

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        class FakeClient:
            def stream(self, method, url, json=None, headers=None):
                return FakeStreamResp()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        monkeypatch.setattr("httpx.Client.stream", FakeClient().stream)
        monkeypatch.setattr("httpx.Client.__enter__", lambda self: FakeClient())
        monkeypatch.setattr("httpx.Client.__exit__", lambda *a: None)

        events = list(LLMClient().chat_stream([{"role": "user", "content": "hi"}]))
        assert events[0] == {"type": "reasoning", "delta": "思考A"}
        assert events[1] == {"type": "content", "delta": "回答B"}
        assert events[2]["type"] == "done"
        assert events[2]["content"] == "回答B"
        assert events[2]["reasoning"] == "思考A"
