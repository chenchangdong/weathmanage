"""顾问 Agent — 意图路由、工具编排与行动卡片。"""

from __future__ import annotations

import json
import re
from typing import Any

from agent_core.advisor_chat import AdvisorChatService
from agent_core.advisor_tools import (
    execute_tool,
    tool_get_diagnosis,
    tool_list_sop_events,
    tool_recommend_mode,
)
from agent_core.chat_context import build_chat_grounding, build_diagnosis_context
from agent_core.journey_state import JOURNEY_STEPS, build_journey_context
from core.config_loader import get_demo_customer, get_risk_level_name, load_customer_profile


class AdvisorStateMachine:
    STATES = {
        'idle': {
            'description': '空闲状态',
            'available_actions': ['diagnose', 'rebalance', 'sop', 'full_service'],
        },
        'diagnosed': {
            'description': '已完成诊断',
            'available_actions': ['rebalance', 'explain_diagnosis', 'sop', 'full_service'],
        },
        'planned': {
            'description': '已生成配仓方案',
            'available_actions': ['explain_plan', 'generate_script', 'sop', 'rebalance'],
        },
        'scripted': {
            'description': '已生成话术',
            'available_actions': ['sop', 'copy_script', 'rebalance'],
        },
    }

    TRANSITIONS = {
        'idle': {
            'diagnose': 'diagnosed',
            'full_service': 'diagnosed',
        },
        'diagnosed': {
            'rebalance': 'planned',
            'full_service': 'planned',
        },
        'planned': {
            'generate_script': 'scripted',
        },
        'scripted': {
            'rebalance': 'planned',
        },
    }

    @classmethod
    def determine_state(cls, journey_ctx: dict[str, Any]) -> str:
        if journey_ctx.get('has_plan'):
            if journey_ctx.get('has_script'):
                return 'scripted'
            return 'planned'
        if journey_ctx.get('has_diagnosis'):
            return 'diagnosed'
        return 'idle'

    @classmethod
    def get_available_actions(cls, state: str) -> list[str]:
        return cls.STATES.get(state, {}).get('available_actions', [])

    @classmethod
    def transition(cls, state: str, action: str) -> str:
        return cls.TRANSITIONS.get(state, {}).get(action, state)


class ConversationStrategy:
    STRATEGIES = {
        'new_customer': {
            'greeting': '首次服务需要先了解客户情况。我可以帮您完成资产诊断、生成配仓方案。',
            'quick_actions': ['诊断', '配仓'],
            'style': 'friendly',
        },
        'returning_customer': {
            'greeting': '上次服务到 {stage}，需要继续吗？',
            'quick_actions': ['继续', '重新诊断'],
            'style': 'efficient',
        },
        'post_allocation': {
            'greeting': '配仓方案已就绪，需要解读或生成话术吗？',
            'quick_actions': ['解读方案', '生成话术'],
            'style': 'supportive',
        },
        'post_script': {
            'greeting': '客户沟通话术已生成，是否需要我帮您推送飞书或查看投后事件？',
            'quick_actions': ['推送飞书', '投后跟进'],
            'style': 'professional',
        },
    }

    @classmethod
    def determine_strategy(cls, journey_ctx: dict[str, Any]) -> dict[str, Any]:
        if journey_ctx.get('has_script'):
            return cls.STRATEGIES['post_script']
        if journey_ctx.get('has_plan'):
            return cls.STRATEGIES['post_allocation']
        if journey_ctx.get('completed_steps') and len(journey_ctx['completed_steps']) > 0:
            return cls.STRATEGIES['returning_customer']
        return cls.STRATEGIES['new_customer']

    @classmethod
    def format_greeting(cls, strategy: dict[str, Any], journey_ctx: dict[str, Any]) -> str:
        greeting = strategy.get('greeting', '')
        stage = journey_ctx.get('stage_label', '—')
        return greeting.format(stage=stage)


class AdvisorAgentService:
    _SERVICE_PATTERNS = (
        r"帮我(完整|全流程)?服务",
        r"完整服务",
        r"全流程",
        r"服务一下",
        r"处理一下",
        r"从头帮我",
    )
    _REBALANCE_PATTERNS = (
        r"配[仓置]",
        r"调仓",
        r"生成方案",
        r"一键",
    )
    _DIAGNOSIS_PATTERNS = (
        r"诊断",
        r"健康度",
        r"什么问题",
    )
    _SOP_PATTERNS = (
        r"投后",
        r"SOP",
        r"事件",
        r"预警",
        r"话术包",
        r"飞书",
        r"推送",
        r"生成内容",
    )
    _NEXT_STEP_PATTERNS = (
        r"下一步",
        r"接下来",
        r"我该做什么",
        r"继续",
    )
    _EXPLAIN_PATTERNS = (
        r"解读",
        r"说明",
        r"解释",
        r"什么意思",
        r"为什么",
    )
    _SCRIPT_PATTERNS = (
        r"话术",
        r"沟通",
        r"对客",
        r"发给客户",
        r"客户话术",
    )

    def __init__(self) -> None:
        self._chat = AdvisorChatService()

    def turn(
        self,
        customer_id: str,
        message: str,
        *,
        history: list[dict[str, str]] | None = None,
        journey: dict[str, Any] | None = None,
        page: str | None = None,
        overview: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            raise ValueError("消息不能为空")

        resolved_id = self._resolve_customer_id(message, customer_id)
        customer = get_demo_customer(resolved_id)
        if not customer:
            raise ValueError(f"客户不存在: {resolved_id}")

        if diagnosis is None and self._matches(message, self._SERVICE_PATTERNS + self._DIAGNOSIS_PATTERNS):
            dx_result = tool_get_diagnosis(resolved_id)
            diagnosis = dx_result.get("diagnosis")

        sop_data = tool_list_sop_events(resolved_id)

        journey_ctx = build_journey_context(
            resolved_id,
            journey=journey,
            page=page,
            diagnosis=diagnosis,
            plan=plan,
        )

        current_state = AdvisorStateMachine.determine_state(journey_ctx)
        strategy = ConversationStrategy.determine_strategy(journey_ctx)

        intent = self._detect_intent(message, current_state)
        tool_results: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []

        if intent == "full_service":
            reply, tool_results, actions = self._handle_full_service(
                resolved_id, customer, diagnosis, journey_ctx, sop_data, current_state
            )
            source = "agent"
        elif intent == "rebalance":
            reply, tool_results, actions = self._handle_rebalance(resolved_id, customer, diagnosis, journey_ctx)
            source = "agent"
        elif intent == "diagnosis":
            reply, tool_results, actions = self._handle_diagnosis(resolved_id, customer, diagnosis, journey_ctx)
            source = "agent"
        elif intent == "sop":
            reply, tool_results, actions = self._handle_sop(resolved_id, customer, sop_data)
            source = "agent"
        elif intent == "next_step":
            reply, tool_results, actions = self._handle_next_step(
                resolved_id, customer, journey_ctx, diagnosis, sop_data, current_state
            )
            source = "agent"
        elif intent == "explain":
            reply, tool_results, actions = self._handle_explain(resolved_id, customer, diagnosis, plan, journey_ctx)
            source = "agent"
        elif intent == "script":
            reply, tool_results, actions = self._handle_script(resolved_id, customer, plan, journey_ctx)
            source = "agent"
        else:
            chat_result = self._chat.chat(
                customer_id=resolved_id,
                message=message,
                history=history,
                overview=overview,
                plan=plan,
                diagnosis=diagnosis,
            )
            grounding = build_chat_grounding(
                resolved_id,
                overview=overview,
                plan=plan,
                diagnosis=diagnosis,
                journey=journey_ctx,
                page=page,
                sop=sop_data,
            )
            reply = chat_result["reply"]
            source = chat_result.get("source", "llm")
            if journey_ctx.get("recommended_next_href"):
                actions.append(self._navigate_action(
                    f"前往{journey_ctx.get('recommended_next_label')}",
                    journey_ctx["recommended_next_href"],
                ))

        if resolved_id != customer_id:
            actions.insert(0, {
                "type": "set_customer",
                "label": f"切换客户：{customer.get('name')}",
                "customer_id": resolved_id,
            })

        journey_ctx = build_journey_context(
            resolved_id,
            journey={**journey_ctx, "stage": journey_ctx.get("stage")},
            page=page,
            diagnosis=diagnosis or (tool_results[0].get("diagnosis") if tool_results else None),
            plan=plan,
        )

        return {
            "reply": reply,
            "reasoning": "",
            "source": source,
            "actions": actions,
            "journey": journey_ctx,
            "tool_results": tool_results,
            "customer_id": resolved_id,
            "intent": intent,
            "state": current_state,
            "strategy": strategy.get('style'),
            "grounding_summary": {
                "customer_name": customer.get("name"),
                "has_diagnosis": journey_ctx.get("has_diagnosis"),
                "has_plan": journey_ctx.get("has_plan"),
                "stage": journey_ctx.get("stage"),
            },
        }

    def execute_confirmed_tool(
        self,
        customer_id: str,
        tool: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = execute_tool(tool, customer_id, params)
        actions: list[dict[str, Any]] = []
        if result.get("ok") and tool == "run_rebalance":
            actions.append({
                "type": "navigate",
                "label": "查看配仓方案",
                "href": "smart_allocation.html",
                "step": "allocation_work",
            })
            actions.append({"type": "agent_prompt", "label": "方案解读", "prompt": "请说明当前配置方案的关键调仓逻辑"})
            actions.append({"type": "agent_prompt", "label": "生成客户话术", "prompt": "请生成一份对客户的沟通话术，介绍当前配仓方案的优势"})
        elif result.get("ok") and tool == "generate_sop_content":
            actions.append(self._navigate_action("打开投后SOP管理台", "sop_agent.html"))
            if result.get("client_script") or (result.get("output") or {}).get("client_script"):
                script = result.get("client_script") or (result.get("output") or {}).get("client_script")
                actions.append({"type": "copy", "label": "复制对客话术", "text": script})
        return {"tool_result": result, "actions": actions}

    @staticmethod
    def _matches(message: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(p, message) for p in patterns)

    def _detect_intent(self, message: str, current_state: str) -> str:
        if self._matches(message, self._SERVICE_PATTERNS):
            return "full_service"
        if self._matches(message, self._SOP_PATTERNS):
            return "sop"
        if self._matches(message, self._NEXT_STEP_PATTERNS):
            return "next_step"
        if self._matches(message, self._EXPLAIN_PATTERNS):
            return "explain"
        if self._matches(message, self._REBALANCE_PATTERNS):
            return "rebalance"
        if self._matches(message, self._DIAGNOSIS_PATTERNS):
            return "diagnosis"
        if self._matches(message, self._SCRIPT_PATTERNS):
            return "script"
        return "chat"

    @staticmethod
    def _resolve_customer_id(message: str, fallback_id: str) -> str:
        current_phrases = ("当前客户", "该客户", "此客户", "这位客户")
        if any(p in message for p in current_phrases):
            return fallback_id
        bare_service = re.search(
            r"帮我(完整|全流程)?服务\s*$|完整服务\s*$|全流程服务\s*$",
            message.strip(),
        )
        if bare_service:
            return fallback_id
        for row in load_customer_profile().get("demo_customers", []):
            name = str(row.get("name") or "")
            short = name.split("（")[0].strip()
            if short and short in message:
                return row["customer_id"]
            if name and name in message:
                return row["customer_id"]
        return fallback_id

    def _handle_full_service(
        self,
        customer_id: str,
        customer: dict[str, Any],
        diagnosis: dict[str, Any] | None,
        journey_ctx: dict[str, Any],
        sop_data: dict[str, Any] | None = None,
        current_state: str = 'idle',
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        dx = tool_get_diagnosis(customer_id)
        mode_rec = tool_recommend_mode(customer_id)
        diagnosis = dx.get("diagnosis") or diagnosis
        summary = dx.get("summary") or {}
        flags = summary.get("flags") or []
        flag_text = "、".join(f["label"] for f in flags[:3]) if flags else "无明显异常标志"

        conclusions = summary.get("conclusions") or []
        conclusion_line = conclusions[0] if conclusions else "建议进入资产诊断查看详情。"

        reply = (
            f"已为<strong>{customer.get('name')}</strong>启动全流程服务。\n\n"
            f"① <strong>盘点发现</strong>：综合评分 {summary.get('composite_score', '—')} 分，"
            f"财富健康标志 {summary.get('flag_count', 0)} 项"
            f"{'（' + flag_text + '）' if flags else ''}。\n"
            f"② <strong>诊断结论</strong>：{conclusion_line}\n"
            f"③ <strong>配仓建议</strong>：推荐「{mode_rec.get('mode_label')}」— {mode_rec.get('reason')}\n"
        )
        sop_events = (sop_data or {}).get("events") or []
        if sop_events:
            reply += (
                f"④ <strong>投后预警</strong>：{len(sop_events)} 条与持仓相关"
                f"（如 {sop_events[0].get('product_name')}·{sop_events[0].get('scenario')}）。\n"
            )

        actions = [
            self._navigate_action("查看资产诊断", "asset_diagnosis.html"),
            {
                "type": "tool",
                "tool": "run_rebalance",
                "label": f"生成{mode_rec.get('mode_label')}",
                "params": {"mode": mode_rec.get("mode")},
                "confirm": True,
                "confirm_text": f"确认为客户 {customer.get('name')} 执行「{mode_rec.get('mode_label')}」？",
            },
            self._navigate_action("进入智能资配 KYC", "smart_allocation_setup.html"),
        ]
        if sop_events:
            pending = [e for e in sop_events if e.get("agent_status") in (None, "pending")]
            actions.append(self._navigate_action("投后SOP跟进", "sop_agent.html"))
            if pending:
                actions.append({
                    "type": "tool",
                    "tool": "generate_sop_content",
                    "label": "生成投后话术包",
                    "params": {"event_id": pending[0].get("event_id")},
                    "confirm": True,
                })

        if journey_ctx.get('has_plan'):
            reply += "\n\n配仓方案已就绪，您可以："
            actions.append({"type": "agent_prompt", "label": "方案解读", "prompt": "请说明当前配置方案的关键调仓逻辑"})
            actions.append({"type": "agent_prompt", "label": "生成客户话术", "prompt": "请生成一份对客户的沟通话术，介绍当前配仓方案的优势"})
        else:
            reply += "\n您可点击下方行动卡片逐步确认，或让我直接生成配仓方案。"

        return reply, [dx, mode_rec, sop_data or {}], actions

    def _handle_rebalance(
        self,
        customer_id: str,
        customer: dict[str, Any],
        diagnosis: dict[str, Any] | None,
        journey_ctx: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        mode_rec = tool_recommend_mode(customer_id)

        reply = (
            f"根据<strong>{customer.get('name')}</strong>当前诊断，"
            f"推荐使用「{mode_rec.get('mode_label')}」。\n"
            f"{mode_rec.get('reason')}\n\n"
            f"点击下方按钮确认后，我将调用配仓引擎生成方案。"
        )

        actions = [{
            "type": "tool",
            "tool": "run_rebalance",
            "label": f"确认生成{mode_rec.get('mode_label')}",
            "params": {"mode": mode_rec.get("mode")},
            "confirm": True,
            "confirm_text": f"确认执行「{mode_rec.get('mode_label')}」？",
        }]

        if journey_ctx.get('has_plan'):
            reply += "\n\n当前已有配仓方案，生成新方案将覆盖原有方案。"

        return reply, [mode_rec], actions

    def _handle_diagnosis(
        self,
        customer_id: str,
        customer: dict[str, Any],
        diagnosis: dict[str, Any] | None,
        journey_ctx: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        dx = tool_get_diagnosis(customer_id)
        diagnosis = dx.get("diagnosis")
        summary = dx.get("summary") or {}
        compact = build_diagnosis_context(diagnosis)
        score_ctx = compact.get("score_context") or {}

        flags = summary.get("flags") or []
        flag_lines = "\n".join(
            f"· {f.get('label')}" for f in flags[:4]
        ) or "· 当前无财富健康异常标志"

        conclusions = summary.get("conclusions") or []
        struct_line = conclusions[0] if conclusions else "结构诊断暂无。"

        reply = (
            f"<strong>{customer.get('name')}</strong>（{get_risk_level_name(customer.get('risk_profile', ''))}）诊断摘要：\n\n"
            f"综合评分 <strong>{summary.get('composite_score', '—')}</strong> 分，"
            f"健康等级 {score_ctx.get('health_label', '—')}。\n\n"
            f"<strong>财富健康标志</strong>\n{flag_lines}\n\n"
            f"<strong>资产配置结构</strong>\n{struct_line}"
        )

        actions = [
            self._navigate_action("打开完整诊断页", "asset_diagnosis.html"),
        ]
        mode_rec = tool_recommend_mode(customer_id)
        if mode_rec.get("mode"):
            actions.append({
                "type": "tool",
                "tool": "run_rebalance",
                "label": f"生成{mode_rec.get('mode_label')}",
                "params": {"mode": mode_rec.get("mode")},
                "confirm": True,
            })

        if journey_ctx.get('has_plan'):
            reply += "\n\n配仓方案已就绪，需要解读方案或生成客户话术吗？"
            actions.append({"type": "agent_prompt", "label": "方案解读", "prompt": "请说明当前配置方案的关键调仓逻辑"})
            actions.append({"type": "agent_prompt", "label": "生成客户话术", "prompt": "请生成一份对客户的沟通话术，介绍当前配仓方案的优势"})

        return reply, [dx, mode_rec], actions

    def _handle_sop(
        self,
        customer_id: str,
        customer: dict[str, Any],
        sop_data: dict[str, Any] | None,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        sop = sop_data or tool_list_sop_events(customer_id)
        events = sop.get("events") or []
        if not events:
            reply = (
                f"<strong>{customer.get('name')}</strong> 当前数据日（{sop.get('data_date') or '—'}）"
                f"无与持仓匹配的投后组合事件。可前往投后SOP管理台执行跑批。"
            )
            return reply, [sop], [self._navigate_action("打开投后SOP", "sop_agent.html")]

        lines = []
        for e in events[:5]:
            status = "已生成" if e.get("has_output") else "待生成"
            lines.append(
                f"· {e.get('product_name')} — {e.get('scenario')}（{status}）"
            )
        reply = (
            f"<strong>{customer.get('name')}</strong> 投后事件（{sop.get('data_date')}）：\n\n"
            + "\n".join(lines)
        )
        if sop.get("pending_count"):
            reply += f"\n\n共 {sop.get('pending_count')} 条待生成内容包。"

        actions = [self._navigate_action("投后SOP管理台", "sop_agent.html")]
        pending = [e for e in events if e.get("agent_status") in (None, "pending")]
        if pending:
            actions.append({
                "type": "tool",
                "tool": "generate_sop_content",
                "label": f"生成「{pending[0].get('product_name')}」话术包",
                "params": {"event_id": pending[0].get("event_id")},
                "confirm": True,
            })
        return reply, [sop], actions

    def _handle_next_step(
        self,
        customer_id: str,
        customer: dict[str, Any],
        journey_ctx: dict[str, Any],
        diagnosis: dict[str, Any] | None,
        sop_data: dict[str, Any] | None,
        current_state: str = 'idle',
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        stage = journey_ctx.get("stage_label") or "—"
        nxt = journey_ctx.get("recommended_next_label")

        strategy = ConversationStrategy.determine_strategy(journey_ctx)
        reply = ConversationStrategy.format_greeting(strategy, journey_ctx)

        actions: list[dict[str, Any]] = []
        if journey_ctx.get("has_plan"):
            actions.append({"type": "agent_prompt", "label": "方案解读", "prompt": "请说明当前配置方案的关键调仓逻辑"})
            actions.append({"type": "agent_prompt", "label": "生成客户话术", "prompt": "请生成一份对客户的沟通话术，介绍当前配仓方案的优势"})
            actions.append(self._navigate_action("查看方案", "smart_allocation.html"))
        elif nxt and journey_ctx.get("recommended_next_href"):
            reply += f" 建议下一步：<strong>{nxt}</strong>。"
            actions.append(self._navigate_action(f"前往{nxt}", journey_ctx["recommended_next_href"]))
        else:
            mode_rec = tool_recommend_mode(customer_id)
            reply += f" 建议执行「{mode_rec.get('mode_label')}」。"
            actions.append({
                "type": "tool",
                "tool": "run_rebalance",
                "label": f"生成{mode_rec.get('mode_label')}",
                "params": {"mode": mode_rec.get("mode")},
                "confirm": True,
            })

        events = (sop_data or {}).get("events") or []
        if events:
            reply += f" 另：有 {len(events)} 条投后预警待关注。"
            actions.append(self._navigate_action("投后跟进", "sop_agent.html"))

        return reply, [sop_data or {}], actions

    def _handle_explain(
        self,
        customer_id: str,
        customer: dict[str, Any],
        diagnosis: dict[str, Any] | None,
        plan: dict[str, Any] | None,
        journey_ctx: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        if journey_ctx.get('has_plan'):
            prompt = f"请为理财经理解读客户{customer.get('name')}的配仓方案。方案数据如下：{json.dumps(plan, ensure_ascii=False)[:2000]}"
            llm_result = self._chat.chat(customer_id=customer_id, message=prompt, plan=plan, diagnosis=diagnosis)
            reply = llm_result.get("reply", f"我来为您解读<strong>{customer.get('name')}</strong>的配仓方案。")
            actions = [
                {"type": "agent_prompt", "label": "生成客户话术", "prompt": "请生成一份对客户的沟通话术，介绍当前配仓方案的优势"},
                self._navigate_action("查看完整方案", "smart_allocation.html"),
            ]
        elif journey_ctx.get('has_diagnosis'):
            if diagnosis is None:
                dx = tool_get_diagnosis(customer_id)
                diagnosis = dx.get("diagnosis")
            prompt = f"请为理财经理解读客户{customer.get('name')}的资产诊断结果。诊断数据如下：{json.dumps(diagnosis, ensure_ascii=False)[:2000]}"
            llm_result = self._chat.chat(customer_id=customer_id, message=prompt, diagnosis=diagnosis)
            reply = llm_result.get("reply", f"我来为您解读<strong>{customer.get('name')}</strong>的诊断结果。")
            actions = [
                self._navigate_action("查看完整诊断", "asset_diagnosis.html"),
                {"type": "agent_prompt", "label": "生成配仓方案", "prompt": "请为我推荐合适的配仓模式并生成方案"},
            ]
        else:
            reply = f"<strong>{customer.get('name')}</strong> 还未进行资产诊断，建议先完成诊断。"
            actions = [
                self._navigate_action("开始诊断", "asset_diagnosis.html"),
                {"type": "agent_prompt", "label": "全流程服务", "prompt": "请为我启动全流程服务"},
            ]
        return reply, [], actions

    def _handle_script(
        self,
        customer_id: str,
        customer: dict[str, Any],
        plan: dict[str, Any] | None,
        journey_ctx: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        if journey_ctx.get('has_plan'):
            prompt = f"请为理财经理生成一份对客户{customer.get('name')}的沟通话术，介绍当前配仓方案的优势和调整建议。方案数据如下：{json.dumps(plan, ensure_ascii=False)[:2000]}"
            llm_result = self._chat.chat(customer_id=customer_id, message=prompt, plan=plan)
            reply = llm_result.get("reply", f"我来为<strong>{customer.get('name')}</strong>生成客户沟通话术。")
            actions = [
                {"type": "copy", "label": "复制话术", "text": reply},
                self._navigate_action("投后跟进", "sop_agent.html"),
            ]
        else:
            reply = f"<strong>{customer.get('name')}</strong> 还没有配仓方案，建议先生成方案后再生成话术。"
            mode_rec = tool_recommend_mode(customer_id)
            actions = [
                {
                    "type": "tool",
                    "tool": "run_rebalance",
                    "label": f"生成{mode_rec.get('mode_label')}",
                    "params": {"mode": mode_rec.get("mode")},
                    "confirm": True,
                },
                self._navigate_action("进入智能资配", "smart_allocation_setup.html"),
            ]
        return reply, [], actions

    @staticmethod
    def _navigate_action(label: str, href: str) -> dict[str, Any]:
        step = next((s for s in JOURNEY_STEPS if s["href"] == href), None)
        return {
            "type": "navigate",
            "label": label,
            "href": href,
            "step": (step or {}).get("id"),
        }
