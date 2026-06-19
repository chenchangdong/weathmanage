"""SOP 6.1 — 指标/规则/组合事件配置与触发评估（独立于投后陪伴）。"""

from __future__ import annotations

import operator
import re
from datetime import date, datetime
from hashlib import md5
from typing import Any, Callable

from core.sop_product_library_service import SopProductLibraryService
from core.config_loader import load_sop_rule_system
from core.sop_event_store import SopEventStore

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

_EXPR_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(>=|<=|!=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*$"
)


def parse_expression(expression: str) -> tuple[str, str, float]:
    m = _EXPR_RE.match(expression or "")
    if not m:
        raise ValueError(f"无效规则表达式: {expression}")
    field, op, raw = m.group(1), m.group(2), m.group(3)
    return field, op, float(raw)


def evaluate_expression(expression: str, metrics: dict[str, Any]) -> bool:
    field, op, threshold = parse_expression(expression)
    raw = metrics.get(field)
    if raw is None:
        return False
    if isinstance(raw, str):
        if op not in ("==", "!="):
            return False
        fn = _OPS[op]
        return fn(raw, str(threshold))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return False
    fn = _OPS.get(op)
    if not fn:
        raise ValueError(f"不支持的操作符: {op}")
    return fn(value, threshold)


def _seed_int(*parts: str) -> int:
    h = md5("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16)


def mock_product_metrics(product_code: str, as_of: date) -> dict[str, Any]:
    """按产品代码与日期生成模拟业绩指标（演示用）。"""
    products = SopProductLibraryService().get_product_map()
    prod = products.get(product_code) or {}
    seed = _seed_int(product_code, as_of.isoformat())
    base_dd = (seed % 900) / 100.0
    daily = round((seed % 700) / 100.0, 2)
    weekly = round(((seed >> 4) % 800) / 100.0, 2)
    max_dd = round(max(daily, weekly, base_dd * 0.9 + 1.5), 2)
    yield_rate = round(2.0 + ((seed >> 8) % 600) / 100.0 - 3.0, 2)
    strategy = prod.get("strategy_type") or prod.get("category") or "多策略"
    return {
        "product_id": product_code,
        "product_code": product_code,
        "product_name": prod.get("product_name", product_code),
        "strategy_type": strategy,
        "asset_type": prod.get("category", ""),
        "daily_drawdown": daily,
        "weekly_drawdown": weekly,
        "max_drawdown": max_dd,
        "yield_rate": yield_rate,
        "drawdown_start_date": as_of.replace(day=max(1, (seed % 25) + 1)).isoformat(),
        "drawdown_days": 3 + (seed % 12),
        "data_date": as_of.isoformat(),
    }


class SopRuleEngine:
    def __init__(self, store: SopEventStore | None = None) -> None:
        self.store = store or SopEventStore()
        self.cfg = load_sop_rule_system()

    def reload(self) -> None:
        load_sop_rule_system.cache_clear()
        self.cfg = load_sop_rule_system()

    def list_indicators(self) -> list[dict[str, Any]]:
        return list(self.cfg.get("indicators") or [])

    def list_groups(self) -> list[dict[str, Any]]:
        return sorted(self.cfg.get("groups") or [], key=lambda g: g.get("sort", 0))

    def list_rules(self) -> list[dict[str, Any]]:
        return list(self.cfg.get("rules") or [])

    def list_composite_events(self) -> list[dict[str, Any]]:
        return list(self.cfg.get("composite_events") or [])

    def evaluate_rule(self, rule: dict[str, Any], metrics: dict[str, Any]) -> bool:
        if not rule.get("enabled", True):
            return False
        try:
            return evaluate_expression(rule["expression"], metrics)
        except ValueError:
            return False

    def run_batch(
        self,
        as_of: date | None = None,
        product_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """6.1.2 事件触发 — 模拟每日跑批，写入事件日志。"""
        today = as_of or date.today()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        products = product_codes or list(SopProductLibraryService().get_product_map().keys())
        rules = [r for r in self.list_rules() if r.get("enabled", True)]
        composites = [c for c in self.list_composite_events() if c.get("enabled", True)]

        rule_hits: list[dict[str, Any]] = []
        composite_events: list[dict[str, Any]] = []

        for code in products:
            metrics = mock_product_metrics(code, today)
            hit_rules: list[dict[str, Any]] = []
            for rule in rules:
                if not self.evaluate_rule(rule, metrics):
                    continue
                desc = (
                    f"规则「{rule['name']}」命中，表达式 {rule['expression']} 成立"
                )
                hit = {
                    "rule_code": rule["code"],
                    "rule_name": rule["name"],
                    "business_type": rule.get("business_type", ""),
                    "business_no": f"{code}_{today.isoformat()}",
                    "product_code": code,
                    "product_name": metrics["product_name"],
                    "level": rule.get("level", "中"),
                    "trigger_description": desc,
                    "trigger_time": ts,
                    "metrics": metrics,
                    "status": 0,
                    "status_label": "0 初始",
                }
                hit_rules.append(hit)
                rule_hits.append(hit)

            for comp in composites:
                codes = comp.get("rule_codes") or []
                matched = [h for h in hit_rules if h["rule_code"] in codes]
                if not matched:
                    continue
                mode = comp.get("match_mode", "any")
                if mode == "all" and len(matched) < len(codes):
                    continue
                primary = matched[0]
                m = primary["metrics"]
                detail = self._format_drawdown_detail(primary, m)
                evt_id = self.store.next_event_id()
                composite_events.append({
                    "event_id": evt_id,
                    "composite_code": comp["code"],
                    "scenario": comp.get("scenario") or comp["name"],
                    "big_class": comp.get("big_class", "售后"),
                    "level": primary.get("level", "中"),
                    "product_code": code,
                    "product_name": m["product_name"],
                    "strategy_type": m.get("strategy_type", ""),
                    "drawdown_detail": detail,
                    "rule_hits": [h["rule_code"] for h in matched],
                    "trigger_time": ts,
                    "data_date": today.isoformat(),
                    "status": 0,
                    "status_label": "0 初始",
                    "agent_status": "pending",
                })

        saved_rules = self.store.append_rule_logs(rule_hits)
        saved_events = self.store.append_composite_events(composite_events)
        return {
            "as_of": today.isoformat(),
            "trigger_time": ts,
            "products_scanned": len(products),
            "rule_hits": len(saved_rules),
            "composite_events": len(saved_events),
            "events": saved_events,
        }

    @staticmethod
    def _format_drawdown_detail(hit: dict[str, Any], metrics: dict[str, Any]) -> str:
        expr = ""
        for rule in load_sop_rule_system().get("rules") or []:
            if rule.get("code") == hit["rule_code"]:
                expr = rule.get("expression", "")
                break
        if "weekly" in expr:
            return (
                f"单周最大回撤 {metrics['weekly_drawdown']}%，"
                f"阈值 {expr.split()[-1].replace('>=', '').replace('>', '')}%"
            )
        if "daily" in expr:
            return (
                f"单日最大回撤 {metrics['daily_drawdown']}%，"
                f"超阈值 {expr.split()[-1]}%"
            )
        return (
            f"近60日最大回撤达 -{metrics['max_drawdown']}%，"
            f"超阈值 -{expr.split()[-1] if expr else '5'}%"
        )

    def query_events(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        big_class: str | None = None,
        keyword: str | None = None,
        drawdown_only: bool = False,
    ) -> list[dict[str, Any]]:
        events = self.store.list_composite_events()
        out: list[dict[str, Any]] = []
        for evt in events:
            d = evt.get("data_date") or evt.get("trigger_time", "")[:10]
            if since and d < since:
                continue
            if until and d > until:
                continue
            if big_class and evt.get("big_class") != big_class:
                continue
            if drawdown_only and "回撤" not in (evt.get("scenario") or ""):
                continue
            if keyword:
                blob = " ".join(
                    str(evt.get(k, ""))
                    for k in ("event_id", "scenario", "product_name", "drawdown_detail")
                )
                if keyword not in blob:
                    continue
            out.append(evt)
        out.sort(key=lambda e: e.get("trigger_time", ""), reverse=True)
        return out
