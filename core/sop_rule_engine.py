"""SOP 6.1 — 指标/规则/组合事件配置与触发评估（独立于投后陪伴）。"""

from __future__ import annotations

import operator
import re
from datetime import date, datetime, timedelta
from hashlib import md5
from typing import Any, Callable

from core.sop_product_library_service import SopProductLibraryService
from core.config_loader import load_sop_agent_system, load_sop_product_library, load_sop_rule_system
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


def _mock_alert_ratio_pct() -> int:
    cfg = load_sop_agent_system().get("mock_performance") or {}
    return max(0, min(int(cfg.get("alert_ratio_pct", 12)), 100))


def _option_label_map(field: str) -> dict[str, str]:
    cfg = load_sop_product_library()
    return {c["code"]: c["label"] for c in cfg.get(field) or [] if c.get("code")}


def _product_snapshot_fields(prod: dict[str, Any]) -> dict[str, str]:
    """产品维度快照：风险属性 category 与资产类型 asset_type 分开携带。"""
    category = (prod.get("category") or "").strip()
    asset_type = (prod.get("asset_type") or "").strip()
    cat_labels = _option_label_map("category_options")
    at_labels = _option_label_map("asset_type_options")
    return {
        "category": category,
        "category_label": cat_labels.get(category, category),
        "asset_type": asset_type,
        "asset_type_label": at_labels.get(asset_type, asset_type),
        "strategy_type": (prod.get("strategy_type") or "").strip(),
    }


def _date_jitter(as_of: date, seed: int, span: float = 1.2) -> float:
    """按 data_date 引入小幅波动，使不同日跑批指标有差异。"""
    mix = (as_of.toordinal() * 17 + seed) % 1000
    return round((mix / 1000.0) * span, 2)


def _normal_metrics(seed: int, prod: dict[str, Any], product_code: str, as_of: date) -> dict[str, Any]:
    """正常业绩：不触发任何规则。"""
    jitter = _date_jitter(as_of, seed, span=0.8)
    daily = round((seed % 25) / 100.0 + jitter * 0.1, 2)
    weekly = round(((seed >> 4) % 40) / 100.0 + jitter * 0.15, 2)
    max_dd = round(1.0 + (seed % 140) / 100.0 + jitter, 2)
    yield_rate = round(3.2 + ((seed >> 8) % 260) / 100.0 + jitter * 0.05, 2)
    snapshot = _product_snapshot_fields(prod)
    return {
        "product_id": product_code,
        "product_code": product_code,
        "product_name": prod.get("product_name", product_code),
        **snapshot,
        "daily_drawdown": daily,
        "weekly_drawdown": weekly,
        "max_drawdown": max_dd,
        "yield_rate": yield_rate,
        "drawdown_start_date": as_of.replace(day=max(1, (seed % 25) + 1)).isoformat(),
        "drawdown_days": 1 + (seed % 5),
        "data_date": as_of.isoformat(),
    }


def _alert_metrics(seed: int, prod: dict[str, Any], product_code: str, as_of: date) -> dict[str, Any]:
    """告警业绩：仅少数产品，且每次只倾向触发一类组合事件。"""
    jitter = _date_jitter(as_of, seed, span=1.5)
    kind = (seed >> 12) % 10
    if kind < 7:
        variant = (seed >> 16) % 3
        if variant == 0:
            daily, weekly, max_dd, yield_rate = 1.2, 7.2, 7.5, 4.2
        elif variant == 1:
            daily, weekly, max_dd, yield_rate = 0.6, 5.6, 5.8, 3.8
        else:
            daily, weekly, max_dd, yield_rate = 0.4, 2.1, 3.6, 4.0
        max_dd = round(max_dd + jitter, 2)
        weekly = round(weekly + jitter * 0.3, 2)
        daily = round(daily + jitter * 0.1, 2)
    else:
        daily, weekly, max_dd, yield_rate = 0.3, 0.8, 1.5, round(0.8 + (seed % 80) / 100.0, 2)
        max_dd = round(max_dd + jitter * 0.2, 2)
        yield_rate = round(yield_rate - jitter * 0.15, 2)
    snapshot = _product_snapshot_fields(prod)
    return {
        "product_id": product_code,
        "product_code": product_code,
        "product_name": prod.get("product_name", product_code),
        **snapshot,
        "daily_drawdown": daily,
        "weekly_drawdown": weekly,
        "max_drawdown": max_dd,
        "yield_rate": yield_rate,
        "drawdown_start_date": as_of.replace(day=max(1, (seed % 25) + 1)).isoformat(),
        "drawdown_days": 3 + (seed % 8),
        "data_date": as_of.isoformat(),
    }


def mock_product_metrics(product_code: str, as_of: date) -> dict[str, Any]:
    """按产品代码与日期生成模拟业绩指标（演示用，多数产品为正常业绩）。"""
    products = SopProductLibraryService().get_product_map()
    prod = products.get(product_code) or {}
    seed = _seed_int(product_code, as_of.isoformat())
    ratio = _mock_alert_ratio_pct()
    is_alert = ratio > 0 and (seed % 100) < ratio
    if is_alert:
        return _alert_metrics(seed, prod, product_code, as_of)
    return _normal_metrics(seed, prod, product_code, as_of)


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
        *,
        replace: bool = False,
        auto_cleanup: bool = True,
    ) -> dict[str, Any]:
        """6.1.2 事件触发 — 模拟每日跑批，写入事件日志。

        默认对同一 data_date + 产品 + 规则/组合事件去重；replace=True 时先清除该日再重跑。
        """
        today = as_of or date.today()
        data_date = today.isoformat()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        products = product_codes or list(SopProductLibraryService().get_product_map().keys())
        rules = [r for r in self.list_rules() if r.get("enabled", True)]
        composites = [c for c in self.list_composite_events() if c.get("enabled", True)]

        purged: dict[str, int] = {}
        if replace:
            purged = self.store.purge_data_date(data_date)

        existing_rule_keys = self.store.existing_rule_log_keys(data_date=data_date)
        existing_event_keys = self.store.existing_composite_keys(data_date=data_date)

        rule_hits: list[dict[str, Any]] = []
        composite_events: list[dict[str, Any]] = []
        skipped_rule_hits = 0
        skipped_composite_events = 0

        for code in products:
            metrics = mock_product_metrics(code, today)
            hit_rules: list[dict[str, Any]] = []
            for rule in rules:
                if not self.evaluate_rule(rule, metrics):
                    continue
                hit = {
                    "rule_code": rule["code"],
                    "rule_name": rule["name"],
                    "business_type": rule.get("business_type", ""),
                    "business_no": f"{code}_{data_date}",
                    "product_code": code,
                    "product_name": metrics["product_name"],
                    "level": rule.get("level", "中"),
                    "trigger_description": (
                        f"规则「{rule['name']}」命中，表达式 {rule['expression']} 成立"
                    ),
                    "trigger_time": ts,
                    "metrics": metrics,
                    "status": 0,
                    "status_label": "0 初始",
                }
                key = self.store.rule_log_key(hit)
                if key in existing_rule_keys:
                    skipped_rule_hits += 1
                    hit_rules.append(hit)
                    continue
                existing_rule_keys.add(key)
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
                event_key = (code, comp["code"], data_date)
                if event_key in existing_event_keys:
                    skipped_composite_events += 1
                    continue
                primary = matched[0]
                m = primary["metrics"]
                detail = self._format_event_detail(
                    primary, m, composite_code=comp.get("code") or ""
                )
                evt_id = self.store.next_event_id()
                existing_event_keys.add(event_key)
                composite_events.append({
                    "event_id": evt_id,
                    "composite_code": comp["code"],
                    "scenario": comp.get("scenario") or comp["name"],
                    "big_class": comp.get("big_class", "售后"),
                    "level": primary.get("level", "中"),
                    "product_code": code,
                    "product_name": m["product_name"],
                    "category": m.get("category", ""),
                    "category_label": m.get("category_label", ""),
                    "asset_type": m.get("asset_type", ""),
                    "asset_type_label": m.get("asset_type_label", ""),
                    "strategy_type": m.get("strategy_type", ""),
                    "drawdown_detail": detail,
                    "rule_hits": [h["rule_code"] for h in matched],
                    "trigger_time": ts,
                    "data_date": data_date,
                    "status": 0,
                    "status_label": "0 初始",
                    "agent_status": "pending",
                })

        saved_rules = self.store.append_rule_logs(rule_hits)
        saved_events = self.store.append_composite_events(composite_events)

        cleanup_result: dict[str, Any] | None = None
        if auto_cleanup:
            cleanup_result = self.cleanup_retention()

        return {
            "as_of": data_date,
            "trigger_time": ts,
            "products_scanned": len(products),
            "rule_hits": len(saved_rules),
            "composite_events": len(saved_events),
            "skipped_rule_hits": skipped_rule_hits,
            "skipped_composite_events": skipped_composite_events,
            "replaced": bool(replace),
            "purged": purged,
            "cleanup": cleanup_result,
            "events": saved_events,
        }

    @staticmethod
    def cleanup_retention(retention_days: int | None = None) -> dict[str, Any]:
        """按保留天数清理历史事件（data_date 早于 cutoff 的记录）。"""
        cfg = load_sop_agent_system().get("event_retention") or {}
        if not cfg.get("enabled", True):
            return {"enabled": False, "removed": {}}
        days = retention_days if retention_days is not None else int(cfg.get("days", 30))
        if days <= 0:
            return {"enabled": True, "retention_days": days, "removed": {}}
        cutoff = date.today() - timedelta(days=days)
        store = SopEventStore()
        removed = store.cleanup_before(cutoff)
        return {
            "enabled": True,
            "retention_days": days,
            "cutoff_before": cutoff.isoformat(),
            "removed": removed,
        }

    @staticmethod
    def _format_event_detail(
        hit: dict[str, Any],
        metrics: dict[str, Any],
        *,
        composite_code: str = "",
    ) -> str:
        """按命中规则/组合事件类型生成预警描述（回撤或收益）。"""
        expr = ""
        for rule in load_sop_rule_system().get("rules") or []:
            if rule.get("code") == hit["rule_code"]:
                expr = rule.get("expression", "")
                break

        is_yield = (
            composite_code == "EVT_YIELD"
            or "yield_rate" in expr
            or hit.get("business_type") == "产品收益预警"
        )
        if is_yield:
            threshold = expr.split()[-1] if expr else "2"
            return (
                f"近60日收益率 {metrics.get('yield_rate', '—')}%，"
                f"低于阈值 {threshold}%"
            )

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

    @staticmethod
    def _format_drawdown_detail(hit: dict[str, Any], metrics: dict[str, Any]) -> str:
        """兼容旧调用；请优先使用 _format_event_detail。"""
        return SopRuleEngine._format_event_detail(hit, metrics)

    def query_events(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        big_class: str | None = None,
        keyword: str | None = None,
        drawdown_only: bool = False,
        composite_code: str | None = None,
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
            if composite_code and evt.get("composite_code") != composite_code:
                continue
            if drawdown_only and "回撤" not in (evt.get("scenario") or ""):
                continue
            if keyword:
                blob = " ".join(
                    str(evt.get(k, ""))
                    for k in (
                        "event_id",
                        "scenario",
                        "product_name",
                        "drawdown_detail",
                        "product_code",
                        "category_label",
                        "asset_type_label",
                    )
                )
                if keyword not in blob:
                    continue
            out.append(evt)
        out.sort(key=lambda e: e.get("trigger_time", ""), reverse=True)
        return out
