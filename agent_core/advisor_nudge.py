"""顾问主动提示 — 进入页面时的 Proactive Nudge。"""

from __future__ import annotations

from typing import Any

from agent_core.advisor_tools import tool_list_sop_events, tool_recommend_mode
from agent_core.context_preload import build_context_bundle, build_inventory_highlight
from agent_core.journey_state import JOURNEY_STEPS, build_journey_context
from core.config_loader import get_demo_customer
from core.sop_batch_scheduler import get_scheduler_status
from core.sop_event_store import SopEventStore


def _navigate(label: str, href: str) -> dict[str, Any]:
    step = next((s for s in JOURNEY_STEPS if s["href"] == href), None)
    return {
        "type": "navigate",
        "label": label,
        "href": href,
        "step": (step or {}).get("id"),
    }


def build_proactive_nudge(
    customer_id: str,
    *,
    page: str | None = None,
    journey: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    page_name = (page or "").split("/")[-1].lower()
    store = SopEventStore()
    global_pending = sum(
        1 for e in store.list_composite_events()
        if e.get("agent_status") in (None, "pending")
    )

    # 投后 SOP 管理台
    if page_name == "sop_agent.html":
        schedule = get_scheduler_status()
        cron = schedule.get("cron_label") or "未配置"
        hint = schedule.get("next_run_hint") or ""
        msg = (
            f"当前事件库待生成内容 <strong>{global_pending}</strong> 条。"
            f"定时跑批：{cron}"
            f"{('，' + hint) if hint else ''}。"
        )
        actions = []
        if global_pending:
            actions.append({
                "type": "tool",
                "tool": "generate_sop_content",
                "label": f"批量生成（{min(global_pending, 20)} 条）",
                "params": {"batch": True, "limit": 20},
                "confirm": True,
                "confirm_text": f"确认批量生成最多 20 条待处理事件的内容包？",
            })
        actions.append(_navigate("打开批量任务配置", "admin/sop_batch_trigger.html"))
        return {"id": "sop_console", "message": msg, "actions": actions}

    # 财富盘点：无选定客户时推荐清单首位
    if page_name == "wealth_inventory.html":
        highlight = build_inventory_highlight()
        if not highlight:
            return None
        flags = highlight.get("flags") or []
        flag_txt = "、".join(f["label"] for f in flags) if flags else "配置健康"
        msg = (
            f"清单共 <strong>{highlight['total_count']}</strong> 位客户，"
            f"<strong>{highlight['need_care_count']}</strong> 位建议介入。"
            f"优先关注 <strong>{highlight['name']}</strong>"
            f"{'（' + flag_txt + '）' if flags else ''}。"
        )
        return {
            "id": "inventory_priority",
            "message": msg,
            "actions": [
                {
                    "type": "set_customer",
                    "label": f"服务 {highlight['name']}",
                    "customer_id": highlight["customer_id"],
                },
                {
                    "type": "agent_prompt",
                    "label": "全流程服务",
                    "prompt": f"帮我完整服务{highlight['name'].split('（')[0]}",
                    "customer_id": highlight["customer_id"],
                },
            ],
        }

    if not customer_id:
        return None

    customer = get_demo_customer(customer_id)
    if not customer:
        return None

    bundle = build_context_bundle(customer_id, page=page, journey=journey, plan=plan)
    journey_ctx = bundle["journey"]
    sop = bundle.get("sop") or {}
    diagnosis = bundle.get("diagnosis") or {}
    flags = diagnosis.get("flags") or []
    has_plan = journey_ctx.get("has_plan")

    # 客户维度投后事件
    customer_events = sop.get("events") or []
    pending_gen = [e for e in customer_events if e.get("agent_status") in (None, "pending")]

    if page_name == "asset_diagnosis.html":
        score = diagnosis.get("composite_score", "—")
        health = (diagnosis.get("score_context") or {}).get("health_label", "—")
        msg = (
            f"<strong>{customer.get('name')}</strong> 综合评分 {score} 分（{health}）。"
        )
        if customer_events:
            msg += f" 另有 <strong>{len(customer_events)}</strong> 条投后预警与持仓相关。"
        elif flags:
            labels = "、".join(f.get("label") or "" for f in flags[:2])
            msg += f" 检测到：{labels}。"
        else:
            msg += " 结构整体正常，可考虑全账户优化。"
        actions = []
        mode_rec = tool_recommend_mode(customer_id)
        actions.append({
            "type": "tool",
            "tool": "run_rebalance",
            "label": f"生成{mode_rec.get('mode_label')}",
            "params": {"mode": mode_rec.get("mode")},
            "confirm": True,
        })
        if customer_events:
            actions.append({
                "type": "agent_prompt",
                "label": "投后事件跟进",
                "prompt": "该客户有哪些投后事件需要处理？",
            })
        return {"id": "diagnosis_page", "message": msg, "actions": actions}

    if page_name in ("smart_allocation_setup.html", "smart_allocation.html"):
        if has_plan:
            msg = f"<strong>{customer.get('name')}</strong> 配仓方案已就绪，需要我解读调仓逻辑或生成对客话术吗？"
            actions = [
                {"type": "agent_prompt", "label": "方案解读", "prompt": "请说明当前配置方案的关键调仓逻辑"},
                {"type": "agent_prompt", "label": "客户话术", "prompt": "请生成一段约200字的客户沟通话术"},
                _navigate("打开智能资配", "smart_allocation.html"),
            ]
        else:
            mode_rec = tool_recommend_mode(customer_id)
            msg = (
                f"尚未生成配仓方案。根据诊断，建议使用「{mode_rec.get('mode_label')}」。"
            )
            actions = [{
                "type": "tool",
                "tool": "run_rebalance",
                "label": f"一键生成{mode_rec.get('mode_label')}",
                "params": {"mode": mode_rec.get("mode")},
                "confirm": True,
            }]
        return {"id": "allocation_page", "message": msg, "actions": actions}

    # 其他旅程页：投后预警回灌
    if customer_events or pending_gen:
        evt = customer_events[0]
        msg = (
            f"<strong>{customer.get('name')}</strong> 持仓相关产品触发投后预警 "
            f"「{evt.get('scenario') or evt.get('composite_code')}」（{evt.get('product_name')}）。"
        )
        actions = [
            {"type": "agent_prompt", "label": "查看投后详情", "prompt": "该客户有哪些投后事件？帮我解读并生成话术"},
            _navigate("打开投后SOP", "sop_agent.html"),
        ]
        if pending_gen:
            actions.append({
                "type": "tool",
                "tool": "generate_sop_content",
                "label": "生成内容包",
                "params": {"event_id": pending_gen[0].get("event_id")},
                "confirm": True,
            })
        return {"id": "sop_customer", "message": msg, "actions": actions}

    # 默认：下一步旅程
    nxt = journey_ctx.get("recommended_next_label")
    if nxt and journey_ctx.get("recommended_next_href"):
        return {
            "id": "journey_next",
            "message": f"当前进度：{journey_ctx.get('stage_label')}。建议下一步：<strong>{nxt}</strong>。",
            "actions": [
                _navigate(f"前往{nxt}", journey_ctx["recommended_next_href"]),
            ],
        }
    return None
