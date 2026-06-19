"""SOP 跑批组合事件 → 财富盘点风险标志。"""

from __future__ import annotations

from typing import Any

from core.config_loader import load_sop_rule_system
from core.sop_event_store import SopEventStore

# 组合事件 code → 财富健康标志 code
_COMPOSITE_TO_FLAG: dict[str, str] = {
    "EVT_DRAWDOWN": "max_drawdown_exceeded",
    "EVT_YIELD": "return_below_expected",
}

_FLAG_META: dict[str, dict[str, str]] = {
    "max_drawdown_exceeded": {"label": "最大回撤超阈值", "severity": "danger"},
    "return_below_expected": {"label": "收益不达预期", "severity": "warn"},
}

_FLAG_HINT_TEMPLATES: dict[str, str] = {
    "max_drawdown_exceeded": (
        "该客户{risk_name}，持仓「{products}」触发最大回撤超阈值预警"
        "（SOP 跑批：{details}），建议关注并评估调仓。"
    ),
    "return_below_expected": (
        "该客户{risk_name}，持仓「{products}」收益不达预期"
        "（SOP 跑批：{details}），建议优化持仓结构。"
    ),
}


def _latest_data_date(events: list[dict[str, Any]]) -> str | None:
    dates = [str(e.get("data_date") or "") for e in events if e.get("data_date")]
    return max(dates) if dates else None


def _enabled_composite_codes() -> set[str]:
    cfg = load_sop_rule_system()
    enabled: set[str] = set()
    for row in cfg.get("composite_events") or []:
        code = str(row.get("code") or "")
        if code in _COMPOSITE_TO_FLAG and row.get("enabled", True):
            enabled.add(code)
    return enabled


def _latest_events_by_product_composite(
    events: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """同一产品 + 组合事件类型保留 data_date 最新一条。"""
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for evt in events:
        product = str(evt.get("product_code") or "")
        composite = str(evt.get("composite_code") or "")
        if not product or not composite:
            continue
        key = (product, composite)
        prev = best.get(key)
        if not prev or (evt.get("data_date") or "") >= (prev.get("data_date") or ""):
            best[key] = evt
    return best


def resolve_sop_wealth_flags(
    holdings: dict[str, float],
    *,
    risk_name: str,
    event_store: SopEventStore | None = None,
) -> list[dict[str, Any]]:
    """根据客户持仓与 SOP 组合事件生成财富风险标志（回撤/收益类）。"""
    held = {code for code, amt in holdings.items() if float(amt or 0) > 0}
    if not held:
        return []

    enabled = _enabled_composite_codes()
    if not enabled:
        return []

    store = event_store or SopEventStore()
    all_events = store.list_composite_events()
    latest_date = _latest_data_date(all_events)
    if not latest_date:
        return []
    events = [e for e in all_events if e.get("data_date") == latest_date]
    latest = _latest_events_by_product_composite(events)

    by_flag: dict[str, list[dict[str, Any]]] = {}
    for (product_code, composite_code), evt in latest.items():
        if composite_code not in enabled or product_code not in held:
            continue
        flag_code = _COMPOSITE_TO_FLAG.get(composite_code)
        if not flag_code:
            continue
        by_flag.setdefault(flag_code, []).append(evt)

    flags: list[dict[str, Any]] = []
    for flag_code in ("max_drawdown_exceeded", "return_below_expected"):
        hits = by_flag.get(flag_code)
        if not hits:
            continue
        hits.sort(key=lambda e: e.get("product_name") or e.get("product_code") or "")
        products = "、".join(
            e.get("product_name") or e.get("product_code") or "" for e in hits
        )
        details = "；".join(
            e.get("drawdown_detail") or e.get("scenario") or "预警触发" for e in hits
        )
        template = _FLAG_HINT_TEMPLATES[flag_code]
        hint = template.format(risk_name=risk_name, products=products, details=details)
        flags.append(
            {
                "code": flag_code,
                "label": _FLAG_META[flag_code]["label"],
                "severity": _FLAG_META[flag_code]["severity"],
                "hint": hint,
                "source": "sop",
                "sop_events": [
                    {
                        "event_id": e.get("event_id"),
                        "product_code": e.get("product_code"),
                        "product_name": e.get("product_name"),
                        "composite_code": e.get("composite_code"),
                        "scenario": e.get("scenario"),
                        "data_date": e.get("data_date"),
                    }
                    for e in hits
                ],
            }
        )
    return flags
