"""SOP 6.2.4 — 话术模板与禁用词过滤。"""

from __future__ import annotations

import re
from typing import Any

from core.config_loader import load_sop_banned_words, load_sop_script_templates


class SopScriptBuilder:
    def __init__(self) -> None:
        self.templates_cfg = load_sop_script_templates()
        self.banned_cfg = load_sop_banned_words()

    def pick_template_key(self, event: dict[str, Any]) -> str:
        scenario = event.get("scenario") or ""
        composite = event.get("composite_code") or ""
        for key, tpl in (self.templates_cfg.get("templates") or {}).items():
            tags = tpl.get("event_tags") or []
            if any(t in scenario for t in tags):
                return key
            if composite == "EVT_YIELD" and key == "yield":
                return key
        return "drawdown"

    def build_from_template(
        self,
        event: dict[str, Any],
        product_info: dict[str, Any],
        research: dict[str, Any],
    ) -> str:
        key = self.pick_template_key(event)
        tpl = (self.templates_cfg.get("templates") or {}).get(key) or {}
        static = product_info.get("static") or {}
        perf = product_info.get("performance") or {}
        rec = research.get("recommendation") or ""
        structured = research.get("structured") or {}
        research_summary = rec or structured.get("outlook") or research.get("conclusion") or ""

        ctx = {
            "product_name": static.get("product_name") or event.get("product_name") or "",
            "drawdown_summary": event.get("drawdown_detail") or "出现一定回撤",
            "weekly_drawdown": perf.get("weekly_drawdown", "—"),
            "max_drawdown": perf.get("max_drawdown", "—"),
            "yield_summary": event.get("drawdown_detail") or "低于预期",
            "research_summary": research_summary,
        }
        greeting = tpl.get("greeting") or "尊敬的客户，您好。"
        body = (tpl.get("body") or "").format(**ctx).strip()
        closing = tpl.get("closing") or "如有疑问欢迎随时联系您的理财经理。"
        return f"{greeting}{body}{closing}"

    def sanitize(self, text: str) -> tuple[str, list[str]]:
        replacements = self.banned_cfg.get("replacements") or {}
        strict = set(self.banned_cfg.get("strict_banned") or [])
        warnings: list[str] = []
        out = text
        for banned, alt in replacements.items():
            if banned in out:
                out = out.replace(banned, alt)
                if banned in strict:
                    warnings.append(f"已替换禁用词「{banned}」→「{alt}」")
        for word in strict:
            if word in out and word not in replacements:
                pattern = re.compile(re.escape(word))
                out = pattern.sub("***", out)
                warnings.append(f"已屏蔽禁用词「{word}」")
        return out, warnings

    def build_client_script(
        self,
        event: dict[str, Any],
        product_info: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        raw = self.build_from_template(event, product_info, research)
        script, warnings = self.sanitize(raw)
        return {
            "text": script,
            "template_key": self.pick_template_key(event),
            "word_count": len(script),
            "compliance_warnings": warnings,
        }
