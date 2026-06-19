"""SOP 6.2 — 四步内容管道（621→622→623→624）。"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from agent_core.llm_client import LLMClient, LLMNotConfiguredError
from core.config_loader import (
    load_sop_agent_system,
    load_sop_research_frameworks,
    load_sop_rule_system,
)
from core.sop_product_info_service import SopProductInfoService
from core.sop_script_builder import SopScriptBuilder


class SopAgentPipeline:
    """6.2 内容包编排：事件描述 → 产品信息 → 投研分析 → 对客话术。"""

    def __init__(self) -> None:
        self.agent_cfg = load_sop_agent_system()
        self.rule_cfg = load_sop_rule_system()
        self.frameworks_cfg = load_sop_research_frameworks()
        self.product_info_svc = SopProductInfoService()
        self.script_builder = SopScriptBuilder()
        self.llm = LLMClient()

    def run(self, event: dict[str, Any], *, use_llm: bool | None = None) -> dict[str, Any]:
        as_of = event.get("data_date") or date.today().isoformat()
        code = event.get("product_code") or ""

        step_622 = self.step_622_product_info(code, as_of)
        step_621 = self.step_621_event_description(event, step_622)
        step_623 = self.step_623_research_analysis(event, step_622, use_llm=use_llm)
        step_624 = self.step_624_client_script(event, step_622, step_623)

        source = step_623.get("source") or "rule_template"
        return {
            "event_id": event.get("event_id"),
            "pipeline_version": "1.0",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "agent_status": "done",
            "source": source,
            "steps": {
                "621_event_description": step_621,
                "622_product_info": step_622,
                "623_research_analysis": step_623,
                "624_client_script": step_624,
            },
            "event_description": step_621.get("text", ""),
            "product_info": step_622,
            "research_analysis": step_623.get("analysis") or {},
            "client_script": step_624.get("text", ""),
            "compliance_warnings": step_624.get("compliance_warnings") or [],
        }

    def step_621_event_description(
        self, event: dict[str, Any], product_info: dict[str, Any]
    ) -> dict[str, Any]:
        """6.2.1 事件获取与描述（Skill Step 3 模板）。"""
        cfg = self.agent_cfg.get("event_description") or {}
        data_date = event.get("data_date") or date.today().isoformat()
        header = (cfg.get("header") or "【{data_date} 售后提醒】").format(
            data_date=data_date
        )
        perf = product_info.get("performance") or {}
        static = product_info.get("static") or {}
        metrics = {
            **perf,
            "product_name": static.get("product_name") or event.get("product_name"),
            "trigger_status": "已触发",
        }

        conclusion_lines: list[str] = []
        detail = event.get("drawdown_detail") or ""
        if detail:
            conclusion_lines.append(
                f"{metrics['product_name']}{detail.rstrip('。')}。"
            )
        else:
            for rule_code in event.get("rule_hits") or []:
                conclusion_lines.append(
                    f"{metrics['product_name']}触发规则 {rule_code}。"
                )

        lines = [
            header,
            "",
            f"- {event.get('scenario') or event.get('composite_code') or '监测事件'}",
            "",
            "- 结论:",
        ]
        for cl in conclusion_lines:
            lines.append(f"  {cl}")

        columns = cfg.get("detail_columns") or []
        if columns:
            lines.append("")
            lines.append("- 明细:")
            header_row = " | ".join(c["label"] for c in columns)
            sep = " | ".join("---" for _ in columns)
            lines.append(f"  {header_row}")
            lines.append(f"  {sep}")
            cells: list[str] = []
            for col in columns:
                key = col["key"]
                val = metrics.get(key, event.get(key, "—"))
                if val in (None, ""):
                    val = "—"
                suffix = col.get("suffix") or ""
                if suffix and val != "—":
                    val = f"{val}{suffix}"
                cells.append(str(val))
            lines.append(f"  {' | '.join(cells)}")

        hits = event.get("rule_hits") or []
        text = "\n".join(lines)
        if hits:
            text += f"\n\n命中规则：{', '.join(hits)}"

        return {
            "step": "6.2.1",
            "text": text,
            "structured": {
                "header": header,
                "scenario": event.get("scenario"),
                "conclusion": conclusion_lines,
                "metrics_row": metrics,
            },
        }

    def step_622_product_info(self, product_code: str, as_of: str) -> dict[str, Any]:
        """6.2.2 产品信息（降级：SOP 产品库 + 模拟业绩）。"""
        pkg = self.product_info_svc.fetch_info_package(product_code, as_of)
        return {"step": "6.2.2", **pkg}

    def _resolve_framework_key(self, strategy_type: str) -> str:
        mapping = self.rule_cfg.get("strategy_frameworks") or {}
        fw_key = mapping.get(strategy_type) or mapping.get("default") or "default"
        frameworks = self.frameworks_cfg.get("frameworks") or {}
        if fw_key not in frameworks:
            return "default"
        return fw_key

    def step_623_research_analysis(
        self,
        event: dict[str, Any],
        product_info: dict[str, Any],
        *,
        use_llm: bool | None = None,
    ) -> dict[str, Any]:
        """6.2.3 投研分析（框架库 + 可选 LLM）。"""
        static = product_info.get("static") or {}
        perf = product_info.get("performance") or {}
        strategy_type = static.get("strategy_type") or event.get("strategy_type") or ""
        fw_key = self._resolve_framework_key(strategy_type)
        fw = (self.frameworks_cfg.get("frameworks") or {}).get(fw_key) or {}

        draft = self._build_research_template(event, static, perf, fw, fw_key, product_info)
        source = "rule_template"
        analysis = draft

        research_cfg = self.agent_cfg.get("research") or {}
        llm_enabled = (
            use_llm
            if use_llm is not None
            else bool(research_cfg.get("use_llm_when_available"))
        )
        if llm_enabled and self.llm.is_configured():
            try:
                analysis = self._enhance_research_with_llm(event, static, perf, fw, draft)
                source = "llm"
            except (LLMNotConfiguredError, Exception):
                analysis = draft

        return {"step": "6.2.3", "source": source, "framework_key": fw_key, "analysis": analysis}

    def _build_research_template(
        self,
        event: dict[str, Any],
        static: dict[str, Any],
        perf: dict[str, Any],
        fw: dict[str, Any],
        fw_key: str,
        product_info: dict[str, Any],
    ) -> dict[str, Any]:
        phenomenon = event.get("drawdown_detail") or "产品出现阶段性回撤"
        product_part = (
            f"产品层面（{fw.get('label', fw_key)}）：{static.get('product_name')}采用"
            f"{static.get('investment_strategy')}。"
            f"{fw.get('product_prompt', '')} "
            f"近一周回撤 {perf.get('weekly_drawdown')}%，最大回撤 {perf.get('max_drawdown')}%。"
        )
        if static.get("conclusion"):
            product_part += f" 产品库结论：{static['conclusion'][:80]}。"
        market_part = fw.get("market_prompt") or "关注宏观与市场波动对产品的传导。"
        market_part = f"市场层面：{market_part}"
        recommendation = fw.get("recommendation_default") or "建议持有观察。"
        if event.get("level") == "高":
            recommendation = (
                "建议与客户充分沟通回撤原因，短期以安抚为主，暂不主动建议大幅调仓。"
            )
        report_note = ""
        if "product_reports" in (product_info.get("degraded") or []):
            report_note = "未检索到该产品专项研报（知识库未接入，已降级为基础画像）"
        conclusion = (
            f"1. 现象描述：{phenomenon}\n"
            f"2. 原因分析：{product_part[:120]}…\n"
            f"3. 前瞻判断及建议：{market_part[:80]}… {recommendation}"
        )
        return {
            "framework": fw_key,
            "framework_label": fw.get("label", fw_key),
            "dimensions": fw.get("dimensions") or [],
            "product_analysis": product_part,
            "market_analysis": market_part,
            "conclusion": conclusion,
            "recommendation": recommendation,
            "structured": {
                "phenomenon": phenomenon,
                "cause": product_part,
                "outlook": f"{market_part} {recommendation}",
            },
            "source_refs": [
                "SOP产品信息库",
                f"分析框架：{fw.get('label', fw_key)}",
            ],
            "report_note": report_note,
        }

    def _enhance_research_with_llm(
        self,
        event: dict[str, Any],
        static: dict[str, Any],
        perf: dict[str, Any],
        fw: dict[str, Any],
        draft: dict[str, Any],
    ) -> dict[str, Any]:
        rcfg = self.agent_cfg.get("research") or {}
        wmin = rcfg.get("word_count_min", 300)
        wmax = rcfg.get("word_count_max", 350)
        prompt = (
            f"你是投后跟踪智能体。基于事件、产品信息与分析框架「{fw.get('label')}」，"
            f"输出 JSON 对象，字段：product_analysis, market_analysis, conclusion, recommendation, "
            f"structured（含 phenomenon, cause, outlook）。"
            f"投研正文 {wmin}-{wmax} 字。禁用「暴跌」等词。\n\n"
            f"事件：{json.dumps(event, ensure_ascii=False)}\n"
            f"产品：{json.dumps(static, ensure_ascii=False)}\n"
            f"业绩：{json.dumps(perf, ensure_ascii=False)}\n"
            f"框架提示：{fw.get('product_prompt')} | {fw.get('market_prompt')}\n"
            f"草稿：{json.dumps(draft, ensure_ascii=False)}"
        )
        reply = self.llm.chat(
            messages=[
                {"role": "system", "content": "只输出 JSON，不要 markdown。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        parsed = json.loads(reply)
        out = dict(draft)
        out.update(parsed)
        out["framework"] = draft.get("framework")
        out["framework_label"] = draft.get("framework_label")
        out["source_refs"] = list(draft.get("source_refs") or []) + ["LLM 增强"]
        return out

    def step_624_client_script(
        self,
        event: dict[str, Any],
        product_info: dict[str, Any],
        research_step: dict[str, Any],
    ) -> dict[str, Any]:
        """6.2.4 对客话术（模板 + 禁用词）。"""
        research = research_step.get("analysis") or {}
        built = self.script_builder.build_client_script(event, product_info, research)
        return {"step": "6.2.4", **built}
