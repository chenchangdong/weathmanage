"""SOP 6.2.5 — 飞书 interactive 卡片组装。"""

from __future__ import annotations

import re
from typing import Any

from core.config_loader import load_sop_agent_system


def _truncate(text: str, limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _plain_summary(markdown: str, limit: int = 280) -> str:
    t = re.sub(r"\|[^|\n]+\|", " ", markdown or "")
    t = re.sub(r"[-]{3,}", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return _truncate(t, limit)


def build_push_card(
    *,
    event: dict[str, Any],
    output: dict[str, Any],
    audience: dict[str, Any],
) -> dict[str, Any]:
    cfg = load_sop_agent_system().get("feishu_push") or {}
    title_tpl = cfg.get("card_title") or "【售后提醒】{scenario} · {product_name}"
    title = title_tpl.format(
        scenario=event.get("scenario") or "售后事件",
        product_name=event.get("product_name") or event.get("product_code") or "—",
        data_date=event.get("data_date") or "—",
    )

    ra = output.get("research_analysis") or {}
    structured = ra.get("structured") or {}
    research_brief = _truncate(
        structured.get("phenomenon")
        or _plain_summary(ra.get("conclusion") or "", 120),
        160,
    )
    cause_brief = _truncate(structured.get("cause") or ra.get("product_analysis") or "", 180)
    outlook_brief = _truncate(
        structured.get("outlook") or ra.get("recommendation") or "", 160
    )
    script = _truncate(output.get("client_script") or "", 420)
    event_brief = _plain_summary(output.get("event_description") or "", 320)

    holding = audience.get("holding_amount")
    holding_text = f"¥{holding:,.0f}" if holding is not None else "—"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**客户**：{audience.get('customer_name')}（{audience.get('risk_profile_name')}）\n"
                    f"**持仓金额**：{holding_text}\n"
                    f"**产品**：{event.get('product_name')} · {event.get('drawdown_detail') or event.get('scenario')}\n"
                    f"**数据日**：{event.get('data_date') or '—'}"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**事件摘要**\n{event_brief}"},
        },
    ]

    if research_brief or cause_brief or outlook_brief:
        elements.append({"tag": "hr"})
        parts = []
        if research_brief:
            parts.append(f"**现象**：{research_brief}")
        if cause_brief:
            parts.append(f"**原因**：{cause_brief}")
        if outlook_brief:
            parts.append(f"**建议**：{outlook_brief}")
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(parts)},
            }
        )

    if script:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**对客话术（可直接转发）**\n{script}"},
            }
        )

    base_url = (cfg.get("app_base_url") or "").rstrip("/")
    event_id = event.get("event_id") or ""
    if base_url and event_id:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "打开 SOP 详情"},
                        "type": "primary",
                        "url": f"{base_url}/frontend/sop_agent.html",
                    }
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": _truncate(title, 80)},
            "template": "red" if event.get("level") == "高" else "orange",
        },
        "elements": elements,
    }
