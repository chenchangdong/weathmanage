"""投后陪伴话术生成 — 每条预警单独生成应对策略与沟通话术。"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from agent_core.llm_client import LLMClient, LLMNotConfiguredError
from core.aftercare_monitor_service import AftercareMonitorService
from core.config_loader import (
    get_demo_customer,
    get_risk_level_name,
    load_aftercare_system,
    load_llm_config,
)


SYSTEM_PROMPT = """你是财富管理投后陪伴助手，面向理财经理为「单条监测预警」生成应对策略与客户沟通话术。

【硬性规则】
1. 只能依据用户消息中的单条预警 JSON 作答，不得编造未提供的行情、产品业绩或客户持仓。
2. 投研类预警：话术面向全体客户，不要写具体客户姓名或持仓。
3. 产品类预警：须结合客户姓名、风险等级与 related_holdings（如有）。
4. 标签含义：【预警】提示风险并给出应对；【安抚】稳定情绪；【增值】增强信任、适度宣传。
5. 须严格遵循「话术内容方向」字段的侧重点。
6. 不要输出 JSON，严格按下方格式（标题必须完全一致）：

## 客户经理应对策略
（面向理财经理，3~5条要点）

## 客户沟通话术
（可直接发送或电话口述，150~280字，语气专业温和）"""

FIELD_SYSTEM_PROMPTS = {
    "advisor_strategy": """你是财富管理投后陪伴助手。请仅针对单条监测预警，为理财经理生成「客户经理应对策略」。
规则：只能依据预警 JSON；投研类不写具体客户姓名；产品类结合客户信息与持仓；遵循标签与话术方向。
直接输出策略正文（3~5条要点），不要标题、不要 JSON。""",
    "customer_script": """你是财富管理投后陪伴助手。请仅针对单条监测预警，生成可直接发送的「客户沟通话术」。
规则：只能依据预警 JSON；投研类面向全体客户；产品类可称呼客户姓名；语气专业温和，150~280字。
直接输出话术正文，不要标题、不要 JSON。""",
}


class AftercareCompanionService:
    def __init__(self) -> None:
        self.monitor = AftercareMonitorService()
        self.system_cfg = load_aftercare_system()
        self.llm_cfg = load_llm_config()
        self.llm = LLMClient()

    @staticmethod
    def is_stream_enabled() -> bool:
        cfg = load_aftercare_system()
        companion = cfg.get("companion") or {}
        return companion.get("stream_enabled", True)

    @staticmethod
    def _parse_sections(text: str) -> dict[str, str]:
        patterns = {
            "advisor_strategy": r"##\s*客户经理应对策略\s*\n(.*?)(?=##|\Z)",
            "customer_script": r"##\s*客户沟通话术\s*\n(.*?)(?=##|\Z)",
        }
        result: dict[str, str] = {}
        for key, pat in patterns.items():
            m = re.search(pat, text, re.DOTALL)
            result[key] = (m.group(1).strip() if m else "")
        return result

    def _build_alert_prompt(
        self,
        zone: str,
        alert: dict[str, Any],
        monitor_result: dict[str, Any],
    ) -> str:
        customer = get_demo_customer(monitor_result["customer_id"]) or {}
        payload: dict[str, Any] = {
            "date": monitor_result["date"],
            "zone": zone,
            "alert": alert,
        }
        if zone == "product":
            payload["customer"] = {
                "name": customer.get("name"),
                "risk_profile_name": get_risk_level_name(customer.get("risk_profile", "")),
            }
        return (
            "【单条投后陪伴预警】\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "请为该条预警生成「客户经理应对策略」与「客户沟通话术」。"
        )

    def _build_field_prompt(
        self,
        zone: str,
        alert: dict[str, Any],
        monitor_result: dict[str, Any],
        field: str,
    ) -> str:
        customer = get_demo_customer(monitor_result["customer_id"]) or {}
        payload: dict[str, Any] = {
            "date": monitor_result["date"],
            "zone": zone,
            "alert": alert,
        }
        if zone == "product":
            payload["customer"] = {
                "name": customer.get("name"),
                "risk_profile_name": get_risk_level_name(customer.get("risk_profile", "")),
            }
        field_label = "客户经理应对策略" if field == "advisor_strategy" else "客户沟通话术"
        return (
            "【单条投后陪伴预警】\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"请仅生成「{field_label}」。"
        )

    def _find_alert(
        self, monitor_result: dict[str, Any], zone: str, rule_id: str
    ) -> dict[str, Any]:
        key = "research_alerts" if zone == "research" else "product_alerts"
        for alert in monitor_result.get(key) or []:
            if alert.get("rule_id") == rule_id:
                return alert
        raise ValueError(f"未找到预警: {zone}/{rule_id}")

    def _fallback_for_alert(
        self,
        zone: str,
        alert: dict[str, Any],
        monitor_result: dict[str, Any],
        *,
        reason: str = "no_key",
        error_detail: str = "",
    ) -> dict[str, str]:
        name = monitor_result.get("customer_name", "客户")
        tags = "、".join(t["label"] for t in alert.get("tags") or [])
        detail = alert.get("mock_detail") or alert.get("indicator", "")
        direction = alert.get("script_direction", "")
        headline = (
            "【规则兜底】未配置大模型 API Key。"
            if reason == "no_key"
            else f"【规则兜底】大模型调用失败：{error_detail}"
        )

        if zone == "research":
            strategy = (
                f"{headline}\n\n"
                f"- 预警标签：{tags}\n"
                f"- 覆盖：{alert.get('coverage', '')}\n"
                f"- 异动：{detail}\n"
                f"- 方向：{direction}\n\n"
                "建议：统一市场解读触达；区分预警/安抚口径；重点客户电话跟进。"
            )
            script = (
                "尊敬的客户，您好。今日市场出现一定波动，我们团队已持续跟踪相关变化。"
                "从长期配置视角看，短期波动属正常范畴，建议保持既定节奏，如有疑问欢迎随时沟通。"
            )
        else:
            strategy = (
                f"{headline}\n\n"
                f"- 客户：{name}\n"
                f"- 预警标签：{tags}\n"
                f"- 覆盖：{alert.get('coverage', '')}\n"
                f"- 异动：{detail}\n"
                f"- 方向：{direction}\n\n"
                "建议：结合持仓说明与基准对比；先安抚再解释；增值类适度提示、避免过度推销。"
            )
            script = (
                f"{name}您好，我们关注到您持仓的相关产品出现需跟进的情况（{alert.get('coverage', '')}）。"
                "我们已为您梳理表现与后续关注点，整体仍符合您的风险承受能力。"
                "如需进一步解读，欢迎随时联系我。"
            )
        return {"advisor_strategy": strategy, "customer_script": script, "source": "fallback"}

    def _llm_limits(self) -> dict[str, Any]:
        chat_cfg = self.llm_cfg.get("chat") or {}
        max_reply = chat_cfg.get("max_reply_tokens")
        limits: dict[str, Any] = {}
        if max_reply is not None:
            limits["max_tokens"] = int(max_reply)
        return limits

    def _generate_alert_scripts(
        self,
        zone: str,
        alert: dict[str, Any],
        monitor_result: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.llm.is_configured():
            fb = self._fallback_for_alert(zone, alert, monitor_result)
            return {
                "advisor_strategy": fb["advisor_strategy"],
                "customer_script": fb["customer_script"],
                "source": "fallback",
            }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_alert_prompt(zone, alert, monitor_result)},
        ]
        try:
            result = self.llm.chat(messages, **self._llm_limits())
            sections = self._parse_sections(result.get("content") or "")
            if not sections.get("advisor_strategy") and not sections.get("customer_script"):
                fb = self._fallback_for_alert(zone, alert, monitor_result, reason="parse_error")
                return {
                    "advisor_strategy": fb["advisor_strategy"],
                    "customer_script": fb["customer_script"],
                    "source": "fallback",
                }
            return {
                "advisor_strategy": sections["advisor_strategy"],
                "customer_script": sections["customer_script"],
                "source": "llm",
                "model": result.get("model"),
            }
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            fb = self._fallback_for_alert(
                zone, alert, monitor_result, reason="llm_error", error_detail=str(exc)
            )
            return {
                "advisor_strategy": fb["advisor_strategy"],
                "customer_script": fb["customer_script"],
                "source": "fallback",
                "error": str(exc),
            }

    def _generate_alert_scripts_stream(
        self,
        zone: str,
        alert: dict[str, Any],
        monitor_result: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        if not self.llm.is_configured():
            fb = self._fallback_for_alert(zone, alert, monitor_result)
            yield {
                "type": "alert_done",
                "zone": zone,
                "rule_id": alert.get("rule_id"),
                "advisor_strategy": fb["advisor_strategy"],
                "customer_script": fb["customer_script"],
                "source": "fallback",
            }
            return

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_alert_prompt(zone, alert, monitor_result)},
        ]
        buffer = ""
        try:
            for chunk in self.llm.chat_stream(messages, **self._llm_limits()):
                if chunk.get("type") == "content":
                    text = chunk.get("delta") or ""
                    buffer += text
                    yield {"type": "delta", "zone": zone, "rule_id": alert.get("rule_id"), "text": text}
                elif chunk.get("type") == "done":
                    content = chunk.get("content") or buffer
                    sections = self._parse_sections(content)
                    if not sections.get("advisor_strategy") and not sections.get("customer_script"):
                        fb = self._fallback_for_alert(zone, alert, monitor_result, reason="parse_error")
                        yield {
                            "type": "alert_done",
                            "zone": zone,
                            "rule_id": alert.get("rule_id"),
                            "advisor_strategy": fb["advisor_strategy"],
                            "customer_script": fb["customer_script"],
                            "source": "fallback",
                        }
                    else:
                        yield {
                            "type": "alert_done",
                            "zone": zone,
                            "rule_id": alert.get("rule_id"),
                            "advisor_strategy": sections["advisor_strategy"],
                            "customer_script": sections["customer_script"],
                            "source": "llm",
                            "model": chunk.get("model"),
                        }
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            fb = self._fallback_for_alert(
                zone, alert, monitor_result, reason="llm_error", error_detail=str(exc)
            )
            yield {
                "type": "alert_done",
                "zone": zone,
                "rule_id": alert.get("rule_id"),
                "advisor_strategy": fb["advisor_strategy"],
                "customer_script": fb["customer_script"],
                "source": "fallback",
                "error": str(exc),
            }

    def _build_zone_items(
        self,
        zone: str,
        alerts: list[dict[str, Any]],
        monitor_result: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str]:
        items: list[dict[str, Any]] = []
        sources: list[str] = []
        for alert in alerts:
            item = dict(alert)
            scripts = self._generate_alert_scripts(zone, alert, monitor_result)
            item["advisor_strategy"] = scripts["advisor_strategy"]
            item["customer_script"] = scripts["customer_script"]
            item["script_source"] = scripts["source"]
            if scripts.get("model"):
                item["llm_model"] = scripts["model"]
            items.append(item)
            sources.append(scripts["source"])
        llm_source = "llm" if sources and all(s == "llm" for s in sources) else (
            "fallback" if sources and all(s == "fallback" for s in sources) else "mixed"
        )
        return items, llm_source

    def _base_response(self, monitor_result: dict[str, Any]) -> dict[str, Any]:
        rd_meta = monitor_result.get("research_meta") or {}
        pd_meta = monitor_result.get("product_meta") or {}
        return {
            "date": monitor_result["date"],
            "customer_id": monitor_result["customer_id"],
            "customer_name": monitor_result.get("customer_name"),
            "stream_enabled": self.is_stream_enabled(),
            "research_zone": {
                "title": rd_meta.get("title", "投研区"),
                "target_customer": rd_meta.get("target_customer", "所有客户"),
                "items": [],
            },
            "product_zone": {
                "title": pd_meta.get("title", "产品区"),
                "target_customer": pd_meta.get("target_customer", "持仓客户"),
                "items": [],
            },
            "llm_source": "fallback",
        }

    def generate(self, customer_id: str) -> dict[str, Any]:
        monitor_result = self.monitor.detect_all(customer_id)
        result = self._base_response(monitor_result)

        research_items, rd_src = self._build_zone_items(
            "research", monitor_result.get("research_alerts") or [], monitor_result
        )
        product_items, pd_src = self._build_zone_items(
            "product", monitor_result.get("product_alerts") or [], monitor_result
        )
        result["research_zone"]["items"] = research_items
        result["product_zone"]["items"] = product_items

        sources = {rd_src, pd_src}
        if sources == {"llm"}:
            result["llm_source"] = "llm"
        elif sources == {"fallback"}:
            result["llm_source"] = "fallback"
        else:
            result["llm_source"] = "mixed"
        return result

    def generate_stream(self, customer_id: str) -> Iterator[dict[str, Any]]:
        monitor_result = self.monitor.detect_all(customer_id)
        result = self._base_response(monitor_result)
        yield {"type": "init", "data": result}

        all_sources: list[str] = []

        for zone, key in (("research", "research_alerts"), ("product", "product_alerts")):
            alerts = monitor_result.get(key) or []
            zone_items: list[dict[str, Any]] = []
            for alert in alerts:
                item = dict(alert)
                item["advisor_strategy"] = ""
                item["customer_script"] = ""
                yield {
                    "type": "alert_start",
                    "zone": zone,
                    "rule_id": alert.get("rule_id"),
                    "alert": item,
                }
                for event in self._generate_alert_scripts_stream(zone, alert, monitor_result):
                    if event["type"] == "delta":
                        yield event
                    elif event["type"] == "alert_done":
                        item["advisor_strategy"] = event["advisor_strategy"]
                        item["customer_script"] = event["customer_script"]
                        item["script_source"] = event["source"]
                        if event.get("model"):
                            item["llm_model"] = event["model"]
                        all_sources.append(event["source"])
                        zone_items.append(item)
                        yield {
                            "type": "alert_done",
                            "zone": zone,
                            "rule_id": alert.get("rule_id"),
                            "item": item,
                        }

            if zone == "research":
                result["research_zone"]["items"] = zone_items
            else:
                result["product_zone"]["items"] = zone_items

        sources_set = set(all_sources)
        if not all_sources:
            llm_source = "fallback"
        elif sources_set == {"llm"}:
            llm_source = "llm"
        elif sources_set == {"fallback"}:
            llm_source = "fallback"
        else:
            llm_source = "mixed"
        result["llm_source"] = llm_source
        yield {"type": "done", "data": result}

    def generate_item_field(
        self,
        customer_id: str,
        zone: str,
        rule_id: str,
        field: str,
    ) -> dict[str, Any]:
        if field not in ("advisor_strategy", "customer_script"):
            raise ValueError(f"不支持的字段: {field}")
        if zone not in ("research", "product"):
            raise ValueError(f"不支持的区域: {zone}")

        monitor_result = self.monitor.detect_all(customer_id)
        alert = self._find_alert(monitor_result, zone, rule_id)
        fb = self._fallback_for_alert(zone, alert, monitor_result)

        if not self.llm.is_configured():
            return {
                "zone": zone,
                "rule_id": rule_id,
                "field": field,
                "content": fb[field],
                "source": "fallback",
            }

        messages = [
            {"role": "system", "content": FIELD_SYSTEM_PROMPTS[field]},
            {
                "role": "user",
                "content": self._build_field_prompt(zone, alert, monitor_result, field),
            },
        ]
        try:
            result = self.llm.chat(messages, **self._llm_limits())
            content = (result.get("content") or "").strip()
            if not content:
                content = fb[field]
                source = "fallback"
            else:
                source = "llm"
            return {
                "zone": zone,
                "rule_id": rule_id,
                "field": field,
                "content": content,
                "source": source,
                "model": result.get("model"),
            }
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            fb_err = self._fallback_for_alert(
                zone, alert, monitor_result, reason="llm_error", error_detail=str(exc)
            )
            return {
                "zone": zone,
                "rule_id": rule_id,
                "field": field,
                "content": fb_err[field],
                "source": "fallback",
                "error": str(exc),
            }

    def generate_item_field_stream(
        self,
        customer_id: str,
        zone: str,
        rule_id: str,
        field: str,
    ) -> Iterator[dict[str, Any]]:
        if field not in ("advisor_strategy", "customer_script"):
            raise ValueError(f"不支持的字段: {field}")
        if zone not in ("research", "product"):
            raise ValueError(f"不支持的区域: {zone}")

        monitor_result = self.monitor.detect_all(customer_id)
        alert = self._find_alert(monitor_result, zone, rule_id)
        fb = self._fallback_for_alert(zone, alert, monitor_result)

        yield {
            "type": "start",
            "zone": zone,
            "rule_id": rule_id,
            "field": field,
        }

        if not self.llm.is_configured():
            yield {
                "type": "done",
                "zone": zone,
                "rule_id": rule_id,
                "field": field,
                "content": fb[field],
                "source": "fallback",
            }
            return

        messages = [
            {"role": "system", "content": FIELD_SYSTEM_PROMPTS[field]},
            {
                "role": "user",
                "content": self._build_field_prompt(zone, alert, monitor_result, field),
            },
        ]
        buffer = ""
        try:
            for chunk in self.llm.chat_stream(messages, **self._llm_limits()):
                if chunk.get("type") == "content":
                    text = chunk.get("delta") or ""
                    buffer += text
                    yield {
                        "type": "delta",
                        "zone": zone,
                        "rule_id": rule_id,
                        "field": field,
                        "text": text,
                    }
                elif chunk.get("type") == "done":
                    content = (chunk.get("content") or buffer).strip()
                    if not content:
                        content = fb[field]
                        source = "fallback"
                    else:
                        source = "llm"
                    yield {
                        "type": "done",
                        "zone": zone,
                        "rule_id": rule_id,
                        "field": field,
                        "content": content,
                        "source": source,
                        "model": chunk.get("model"),
                    }
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            fb_err = self._fallback_for_alert(
                zone, alert, monitor_result, reason="llm_error", error_detail=str(exc)
            )
            yield {
                "type": "done",
                "zone": zone,
                "rule_id": rule_id,
                "field": field,
                "content": fb_err[field],
                "source": "fallback",
                "error": str(exc),
            }
