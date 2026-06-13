"""投后陪伴监测 — 模拟市场与产品异动（无真实行情 API）。"""

from __future__ import annotations

from datetime import date
from hashlib import md5
from typing import Any

from core.config_loader import (
    get_demo_customer,
    get_product_map,
    load_aftercare_system,
)
from core.data_store import get_customer_holdings


def _tag_labels(cfg: dict[str, Any], tag_keys: list[str]) -> list[dict[str, str]]:
    legend = cfg.get("tag_legend") or {}
    out: list[dict[str, str]] = []
    for key in tag_keys:
        item = legend.get(key) or {}
        out.append({"key": key, "label": item.get("label", key)})
    return out


def _enabled_rules(section: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (section.get("rules") or []) if r.get("enabled", True)]


def _seed(*parts: str) -> int:
    h = md5("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16)


def _pick_rules(rules: list[dict[str, Any]], seed: int, count: int) -> list[dict[str, Any]]:
    """按 seed 选取 count 条不重复规则（count 为 1 或 2）。"""
    if not rules or count <= 0:
        return []
    start = seed % len(rules)
    picked: list[dict[str, Any]] = []
    for i in range(min(count, len(rules))):
        picked.append(rules[(start + i) % len(rules)])
    return picked


class AftercareMonitorService:
    """根据配置规则模拟当日触发的投研/产品预警。"""

    def __init__(self) -> None:
        self.cfg = load_aftercare_system()

    def _mock_research_detail(self, rule_id: str, today: str) -> str:
        samples = {
            "rd_ashares": "沪深300单日跌幅 -3.2%，中证500 -3.5%",
            "rd_hk": "恒生指数 -3.6%，恒生科技 -4.2%",
            "rd_us": "标普500 -3.1%，纳斯达克 -3.4%",
            "rd_bond": "10年国债期货连续下跌 0.12%",
            "rd_gold": "沪金主力 -3.3%，COMEX黄金 -3.1%",
            "rd_commodity": "能源/黑色/有色等多品种单日跌幅超 3%",
            "rd_quant": "量化策略成交量骤降，拥挤度指标异常",
            "rd_macro": "央行货币政策出现重大调整信号",
            "rd_strategy_cta": "CTA策略规则变更，部分品种流动性收紧",
            "rd_strategy_snowball": "雪球产品敲入距离收窄，需关注流动性",
        }
        base = samples.get(rule_id, "监测指标触及阈值")
        return f"{base}（模拟·{today}）"

    def detect_research_alerts(self, as_of: date | None = None) -> list[dict[str, Any]]:
        """投研驱动 — 市场整体，不绑定客户；模拟触发 1~2 条。"""
        today = (as_of or date.today()).isoformat()
        section = self.cfg.get("research_driven") or {}
        rules = _enabled_rules(section)
        seed = _seed("research", today)
        count = 1 + (seed % 2)
        trigger_rules = _pick_rules(rules, seed, count)

        alerts: list[dict[str, Any]] = []
        for rule in trigger_rules:
            alerts.append(
                {
                    "rule_id": rule["id"],
                    "layer": rule.get("layer", ""),
                    "coverage": rule.get("coverage", ""),
                    "indicator": rule.get("indicator", ""),
                    "tags": _tag_labels(self.cfg, rule.get("tags") or []),
                    "script_direction": rule.get("script_direction", ""),
                    "mock_detail": self._mock_research_detail(rule["id"], today),
                }
            )
        return alerts

    def _customer_holdings_summary(self, customer_id: str) -> list[dict[str, Any]]:
        data = get_customer_holdings(customer_id) or {}
        holdings = data.get("holdings") or {}
        product_map = get_product_map()
        items: list[dict[str, Any]] = []
        for code, amount in holdings.items():
            if (amount or 0) <= 0.01:
                continue
            prod = product_map.get(code) or {}
            items.append(
                {
                    "code": code,
                    "name": prod.get("name", code),
                    "amount": amount,
                    "asset_type": prod.get("asset_type", ""),
                }
            )
        return items

    def _mock_product_detail(self, rule_id: str, customer_id: str, holdings: list[dict[str, Any]]) -> str:
        names = "、".join(h["name"] for h in holdings[:3]) or "相关持仓"
        samples = {
            "pd_perf_outperform": f"客户持有 {names} 等产品，近3月连续跑赢基准",
            "pd_sector_inflow": f"AI/新能源板块3日上涨，客户持有 {names}",
            "pd_dd_active_quant_cta": f"{names} 单周回撤 2.3%，最大回撤 3.2%",
            "pd_dd_active_dividend": f"红利策略产品单周回撤 3.2%，最大回撤 5.1%",
            "pd_dd_active_subjective_long": f"{names} 单周回撤 5.2%，最大回撤 8.1%",
            "pd_dd_active_multi": f"多策略产品单周回撤 4.1%，最大回撤 6.2%",
            "pd_dd_cautious_multi": f"多策略相对回撤 2.1%，绝对回撤 3.2%",
            "pd_dd_cautious_preferred_stock": f"优选股票产品单周回撤 5.3%",
            "pd_dd_low_corr_cta": f"CTA 策略单周回撤 3.1%",
            "pd_dd_low_corr_t0_neutral": f"T0/中性策略单周回撤 1.6%",
            "pd_dd_fixed_income_like": f"类固收产品单周回撤 1.2%",
            "pd_dd_discretionary_a": f"类全委A档产品最大回撤 2.5%",
            "pd_dd_discretionary_b": f"类全委B档产品最大回撤 7.2%",
            "pd_dd_discretionary_c": f"类全委C档产品最大回撤 9.1%",
            "pd_return_target": "产品距到期1个月，收益目标达成情况需检视",
            "pd_suixinding": "随心定产品需结合最新投研结论跟进",
            "pd_snowball": "雪球产品敲入风险上升，需结合投研结论跟进",
        }
        return samples.get(rule_id, f"客户 {customer_id} 持仓触发监测阈值")

    def detect_product_alerts(
        self, customer_id: str, as_of: date | None = None
    ) -> list[dict[str, Any]]:
        """产品驱动 — 与具体客户持仓相关；模拟触发 1~2 条。"""
        customer = get_demo_customer(customer_id)
        if not customer:
            raise ValueError(f"客户不存在: {customer_id}")

        today = (as_of or date.today()).isoformat()
        section = self.cfg.get("product_driven") or {}
        rules = _enabled_rules(section)
        holdings = self._customer_holdings_summary(customer_id)
        if not holdings:
            return []

        seed = _seed("product", customer_id, today)
        count = 1 + (seed % 2)
        trigger_rules = _pick_rules(rules, seed, count)

        alerts: list[dict[str, Any]] = []
        for rule in trigger_rules:
            alerts.append(
                {
                    "rule_id": rule["id"],
                    "layer": rule.get("layer", ""),
                    "coverage": rule.get("coverage", ""),
                    "indicator": rule.get("indicator", ""),
                    "tags": _tag_labels(self.cfg, rule.get("tags") or []),
                    "script_direction": rule.get("script_direction", ""),
                    "mock_detail": self._mock_product_detail(rule["id"], customer_id, holdings),
                    "related_holdings": holdings[:5],
                }
            )
        return alerts

    def detect_all(self, customer_id: str, as_of: date | None = None) -> dict[str, Any]:
        customer = get_demo_customer(customer_id)
        if not customer:
            raise ValueError(f"客户不存在: {customer_id}")
        today = (as_of or date.today()).isoformat()
        research = self.detect_research_alerts(as_of=as_of)
        product = self.detect_product_alerts(customer_id, as_of=as_of)
        rd_sec = self.cfg.get("research_driven") or {}
        pd_sec = self.cfg.get("product_driven") or {}
        return {
            "date": today,
            "customer_id": customer_id,
            "customer_name": customer.get("name", customer_id),
            "research_alerts": research,
            "product_alerts": product,
            "research_meta": {
                "title": rd_sec.get("title", "投研区"),
                "target_customer": rd_sec.get("target_customer", "所有客户"),
            },
            "product_meta": {
                "title": pd_sec.get("title", "产品区"),
                "target_customer": pd_sec.get("target_customer", "持仓客户"),
            },
        }
