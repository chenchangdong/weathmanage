"""Advisor chat — LLM copilot with grounded context."""

from __future__ import annotations

import json
from typing import Any

from agent_core.chat_context import build_chat_grounding
from agent_core.llm_client import LLMClient, LLMNotConfiguredError
from core.config_loader import load_llm_config


SYSTEM_PROMPT = """你是「四笔钱智能投顾」理财经理副驾驶助手。

【硬性规则】
1. 只能依据用户消息附带的 grounding JSON 中的数字与事实作答，不得编造持仓、金额、比例、产品名。
2. 若 grounding 中无某项数据，明确说「当前上下文未提供」，不要猜测。
3. 涉及具体调仓金额、买卖建议时，应说明「最终以系统配仓引擎验算结果为准」。
4. 解释术语：在区间内=占比落在模型阈值带内；次优解=方案目标占比仍可能越界；超配/低配=相对模型基准建议减配/增配。
5. 不要输出 JSON。

【篇幅与格式】
1. 正文控制在 250~450 汉字；用户要求「详细/全面」时可至 600 字。
2. 结构：先 1~2 句结论，再用 3~4 条要点展开（每条不超过 40 字）；避免冗长段落堆砌。
3. 不要复述 grounding 全文；可引用与问题相关的 2~3 个关键数字或产品。
4. 避免套话开场，直接作答；面向理财经理，语气简洁专业。
5. 可执行建议 2~3 条；必要时用自然段落或有序列表。"""


class AdvisorChatService:
    system_prompt = SYSTEM_PROMPT

    def __init__(self) -> None:
        self.cfg = load_llm_config()
        self.llm = LLMClient()

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.llm.is_configured(),
            "model": self.llm.model,
            "base_url": self.llm.base_url,
            "provider": self.cfg.get("provider", "openai_compatible"),
            "chat_enabled": self.cfg.get("scenes", {}).get("advisor_chat", {}).get("enabled", True),
            "thinking_enabled": self.llm.enable_thinking,
            "stream_enabled": True,
        }

    def _llm_limits(self) -> dict[str, int | None]:
        chat_cfg = self.cfg.get("chat") or {}
        max_reply = chat_cfg.get("max_reply_tokens")
        thinking = chat_cfg.get("thinking_budget")
        return {
            "max_tokens": int(max_reply) if max_reply is not None else None,
            "thinking_budget": int(thinking) if thinking is not None else None,
        }

    def _build_messages(
        self,
        message: str,
        history: list[dict[str, str]] | None,
        grounding: dict[str, Any],
    ) -> list[dict[str, str]]:
        max_turns = int(self.cfg.get("chat", {}).get("max_history_turns", 6))
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        trimmed = (history or [])[-max_turns * 2 :]
        for item in trimmed:
            role = item.get("role", "user")
            content = (item.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        user_content = (
            f"【业务上下文 grounding】\n{json.dumps(grounding, ensure_ascii=False, indent=2)}\n\n"
            f"【理财经理提问】\n{message}"
        )
        messages.append({"role": "user", "content": user_content})
        return messages

    def _finalize_llm_reply(self, content: str) -> str:
        disclaimer = self.cfg.get("chat", {}).get("disclaimer", "")
        reply = (content or "").strip()
        if disclaimer and reply and disclaimer not in reply:
            reply = f"{reply}\n\n—— {disclaimer}"
        return reply

    def chat(
        self,
        customer_id: str,
        message: str,
        history: list[dict[str, str]] | None = None,
        overview: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            raise ValueError("消息不能为空")

        grounding = build_chat_grounding(
            customer_id, overview=overview, plan=plan, diagnosis=diagnosis
        )
        disclaimer = self.cfg.get("chat", {}).get("disclaimer", "")

        if not self.llm.is_configured():
            return {
                "reply": self._fallback_reply(message, grounding, disclaimer),
                "reasoning": "",
                "source": "fallback",
                "model": None,
                "usage": {},
                "grounding_summary": self._grounding_summary(grounding),
            }

        messages = self._build_messages(message, history, grounding)
        limits = self._llm_limits()

        try:
            result = self.llm.chat(messages, **limits)
            reply = self._finalize_llm_reply(result["content"])
            reasoning = (result.get("reasoning") or "").strip()
            return {
                "reply": reply,
                "reasoning": reasoning,
                "source": "llm",
                "model": result.get("model"),
                "usage": result.get("usage") or {},
                "grounding_summary": self._grounding_summary(grounding),
            }
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            err = str(exc)
            fallback = self._fallback_reply(
                message, grounding, disclaimer, reason="llm_error", error_detail=err
            )
            return {
                "reply": fallback,
                "reasoning": "",
                "source": "fallback",
                "model": None,
                "usage": {},
                "grounding_summary": self._grounding_summary(grounding),
                "error": err,
            }

    def chat_stream(
        self,
        customer_id: str,
        message: str,
        history: list[dict[str, str]] | None = None,
        overview: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        diagnosis: dict[str, Any] | None = None,
    ):
        message = (message or "").strip()
        if not message:
            raise ValueError("消息不能为空")

        grounding = build_chat_grounding(
            customer_id, overview=overview, plan=plan, diagnosis=diagnosis
        )
        disclaimer = self.cfg.get("chat", {}).get("disclaimer", "")

        if not self.llm.is_configured():
            yield {
                "type": "done",
                "reply": self._fallback_reply(message, grounding, disclaimer),
                "reasoning": "",
                "source": "fallback",
                "model": None,
                "usage": {},
                "grounding_summary": self._grounding_summary(grounding),
            }
            return

        messages = self._build_messages(message, history, grounding)
        limits = self._llm_limits()
        try:
            for chunk in self.llm.chat_stream(messages, **limits):
                if chunk.get("type") == "done":
                    reply = self._finalize_llm_reply(chunk.get("content") or "")
                    yield {
                        "type": "done",
                        "reply": reply,
                        "reasoning": (chunk.get("reasoning") or "").strip(),
                        "source": "llm",
                        "model": chunk.get("model"),
                        "usage": chunk.get("usage") or {},
                        "grounding_summary": self._grounding_summary(grounding),
                    }
                else:
                    yield chunk
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            err = str(exc)
            yield {
                "type": "done",
                "reply": self._fallback_reply(
                    message, grounding, disclaimer, reason="llm_error", error_detail=err
                ),
                "reasoning": "",
                "source": "fallback",
                "model": None,
                "usage": {},
                "grounding_summary": self._grounding_summary(grounding),
                "error": err,
            }

    @staticmethod
    def _grounding_summary(grounding: dict[str, Any]) -> dict[str, Any]:
        cust = grounding.get("customer") or {}
        ov = grounding.get("asset_overview") or {}
        pl = grounding.get("allocation_plan") or {}
        dx = grounding.get("asset_diagnosis") or {}
        return {
            "customer_name": cust.get("name"),
            "has_overview": ov.get("available", False),
            "has_plan": pl.get("available", False),
            "has_diagnosis": dx.get("available", False),
        }

    def _fallback_reply(
        self,
        message: str,
        grounding: dict[str, Any],
        disclaimer: str,
        *,
        reason: str = "no_key",
        error_detail: str = "",
    ) -> str:
        cust = grounding.get("customer") or {}
        ov = grounding.get("asset_overview") or {}
        pl = grounding.get("allocation_plan") or {}
        dx = grounding.get("asset_diagnosis") or {}
        name = cust.get("name", "客户")
        if reason == "llm_error":
            headline = "【大模型调用失败】以下为基于系统数据的规则兜底说明。"
            if "timed out" in error_detail.lower() or "timeout" in error_detail.lower():
                headline += (
                    " 推理模型响应较慢，请稍后重试，"
                    "或在 config/llm_config.yaml 增大 timeout_seconds / 改用 qwen-plus。"
                )
            elif error_detail:
                headline += f"（{error_detail}）"
        else:
            headline = "【规则兜底模式】未检测到大模型 API Key，以下为基于系统数据的简要说明。"
        lines = [
            headline,
            f"客户：{name}（{cust.get('risk_profile_name', '')}）",
        ]
        if ov.get("available"):
            health = (ov.get("health") or {}).get("label", "")
            addon = ov.get("idle_cash") or 0
            addon_text = f"，追加持仓 {addon:,.0f} 元" if addon > 0.01 else ""
            lines.append(
                f"资产检视：总资产 {ov.get('total_assets', 0):,.0f} 元{addon_text}，配置健康度 {health}。"
            )
            off_band = [
                c["category_name"]
                for c in (ov.get("categories") or [])
                if not c.get("in_band", True)
            ]
            if off_band:
                lines.append(f"当前占比超出模型区间的大类：{'、'.join(off_band)}。")
        else:
            lines.append("尚未加载资产检视数据，请先在页面选择客户。")

        if pl.get("available"):
            lines.append(
                f"已加载配置方案（模式：{pl.get('mode')}）。"
                f"校验备注：{'；'.join(pl.get('validation_notes') or [])}"
            )
        else:
            lines.append("尚未生成智能配置方案，可先执行「全账户一键智能最优配置」。")

        if dx.get("available"):
            lines.append(
                f"资产诊断：综合评分 {dx.get('composite_score')} 分，"
                f"财富健康标志 {len(dx.get('flags') or [])} 项。"
            )
            for c in (dx.get("conclusions") or [])[:3]:
                lines.append(f"- {c}")

        lines.append(f"您的问题：{message}")
        if reason == "no_key":
            lines.append(
                "如需 AI 深度解读，请配置环境变量 LLM_API_KEY 并重启服务。"
            )
        if disclaimer:
            lines.append(f"—— {disclaimer}")
        return "\n".join(lines)
