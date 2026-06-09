"""OpenAI-compatible LLM HTTP client."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx

from core.config_loader import load_llm_config


class LLMNotConfiguredError(RuntimeError):
    """API Key 或端点未配置。"""


class LLMClient:
    def __init__(self) -> None:
        self.cfg = load_llm_config()
        self.api_key = self._resolve_api_key()
        self.base_url = self.cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.model = self.cfg.get("model", "gpt-4o-mini")
        self.temperature = float(self.cfg.get("temperature", 0.4))
        self.max_tokens = int(self.cfg.get("max_tokens", 1200))
        self.timeout = float(self.cfg.get("timeout_seconds", 45))
        self.enable_thinking = bool(self.cfg.get("enable_thinking", False))
        budget = self.cfg.get("thinking_budget")
        self.thinking_budget = int(budget) if budget is not None else None

    @staticmethod
    def _resolve_api_key() -> str:
        cfg = load_llm_config()
        for env_name in (
            cfg.get("api_key_env", "LLM_API_KEY"),
            cfg.get("api_key_fallback_env", "OPENAI_API_KEY"),
        ):
            val = os.environ.get(env_name, "").strip()
            if val:
                return val
        return ""

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking_budget: int | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if self.enable_thinking:
            payload["enable_thinking"] = True
            budget = thinking_budget if thinking_budget is not None else self.thinking_budget
            if budget is not None:
                payload["thinking_budget"] = budget
        return payload

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _normalize_message(message: dict[str, Any]) -> dict[str, str]:
        content = (message.get("content") or "").strip()
        reasoning = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        ).strip()
        if not content and reasoning:
            content = reasoning
            reasoning = ""
        return {"content": content, "reasoning": reasoning}

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise LLMNotConfiguredError(
                "未配置大模型 API Key，请设置环境变量 LLM_API_KEY 或 OPENAI_API_KEY"
            )

        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            stream=False,
        )
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._headers(self.api_key))
            resp.raise_for_status()
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        normalized = self._normalize_message(message)
        return {
            "content": normalized["content"],
            "reasoning": normalized["reasoning"],
            "model": data.get("model", self.model),
            "usage": usage,
        }

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking_budget: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        if not self.api_key:
            raise LLMNotConfiguredError(
                "未配置大模型 API Key，请设置环境变量 LLM_API_KEY 或 OPENAI_API_KEY"
            )

        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            stream=True,
        )
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        model = self.model
        usage: dict[str, Any] = {}

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                url,
                json=payload,
                headers=self._headers(self.api_key),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("model"):
                        model = obj["model"]
                    if obj.get("usage"):
                        usage = obj["usage"]
                    delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                    reasoning_delta = delta.get("reasoning_content")
                    if reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                        yield {"type": "reasoning", "delta": reasoning_delta}
                    content_delta = delta.get("content")
                    if content_delta:
                        content_parts.append(content_delta)
                        yield {"type": "content", "delta": content_delta}

        normalized = self._normalize_message({
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts),
        })
        yield {
            "type": "done",
            "content": normalized["content"],
            "reasoning": normalized["reasoning"],
            "model": model,
            "usage": usage,
        }
