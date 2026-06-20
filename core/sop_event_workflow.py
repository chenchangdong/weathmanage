"""投后 SOP 事件流程状态（智能生成 → 飞书推送）展示辅助。"""

from __future__ import annotations

from typing import Any

FLOW_TOOLTIP = (
    "流程：跑批识别 → 智能生成内容包 → 飞书推送给客户经理。"
    "「生成」表示内容包是否就绪；「推送」表示飞书是否送达。"
    "旧字段「0 初始 / 1 已确认」已弃用，「已确认」并不表示已推送。"
)

_AGENT: dict[str | None, tuple[str, str]] = {
    None: ("待生成", "pending"),
    "pending": ("待生成", "pending"),
    "running": ("生成中", "running"),
    "done": ("已生成", "done"),
    "failed": ("生成失败", "failed"),
}

_PUSH: dict[str | None, tuple[str, str]] = {
    None: ("待推送", "waiting"),
    "": ("待推送", "waiting"),
    "skipped": ("未推送", "skipped"),
    "sent": ("已推送", "sent"),
    "partial": ("部分推送", "partial"),
    "failed": ("推送失败", "failed"),
}


def workflow_display(evt: dict[str, Any]) -> dict[str, Any]:
    """根据 agent_status / push_status 计算 UI 展示字段。"""
    agent_status = evt.get("agent_status")
    push_status = evt.get("push_status")
    agent_label, agent_class = _AGENT.get(agent_status, ("待生成", "pending"))
    if agent_status != "done":
        push_label, push_class = ("—", "none")
    else:
        push_label, push_class = _PUSH.get(push_status, ("待推送", "waiting"))

    return {
        "agent_label": agent_label,
        "agent_class": agent_class,
        "push_label": push_label,
        "push_class": push_class,
        "tooltip": FLOW_TOOLTIP,
        "legacy_status_label": evt.get("status_label"),
    }
