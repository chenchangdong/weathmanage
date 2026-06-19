"""SOP 6.2.2 — 产品信息（降级：SOP 产品信息库 + 模拟业绩）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.config_loader import load_sop_agent_system
from core.sop_product_library_service import SopProductLibraryService
from core.sop_rule_engine import mock_product_metrics


class SopProductInfoService:
    """无评价库/知识库时的降级数据源。"""

    def __init__(self) -> None:
        self.cfg = load_sop_agent_system()
        self.product_lib = SopProductLibraryService()

    def fetch_static(self, product_code: str) -> dict[str, Any]:
        prod = self.product_lib.get_product(product_code) or {}
        if not prod:
            for row in self.product_lib.get_config().get("products") or []:
                if row.get("product_id") == product_code:
                    prod = row
                    break
        mgr_name = prod.get("manager_name") or prod.get("management_org") or "—"
        category_map = {
            c["code"]: c["label"]
            for c in self.product_lib.get_config().get("category_options") or []
        }
        asset_type_map = {
            c["code"]: c["label"]
            for c in self.product_lib.get_config().get("asset_type_options") or []
        }
        cat = prod.get("category") or ""
        asset_type = (prod.get("asset_type") or "").strip()
        strategy_type = (prod.get("strategy_type") or "").strip()
        return {
            "product_id": product_code,
            "product_name": prod.get("product_name", product_code),
            "product_code": prod.get("product_code", product_code),
            "product_type": category_map.get(cat, cat or "—"),
            "category": cat,
            "category_label": category_map.get(cat, cat or "—"),
            "asset_type": asset_type,
            "asset_type_label": asset_type_map.get(asset_type, asset_type or "—"),
            "strategy_type": strategy_type or "—",
            "fund_manager": mgr_name,
            "investment_strategy": prod.get("conclusion")
            or ((strategy_type or category_map.get(cat, cat)) + "策略" if (strategy_type or cat) else "—"),
            "benchmark": "中证800",
            "management_org": mgr_name,
            "risk_level": prod.get("rating") or "—",
            "setup_date": prod.get("setup_date") or "",
            "risk_note": prod.get("risk") or "",
            "score": prod.get("score"),
            "conclusion": prod.get("conclusion") or "",
        }

    def fetch_performance(self, product_code: str, as_of: str) -> dict[str, Any]:
        d = date.fromisoformat(as_of[:10])
        m = mock_product_metrics(product_code, d)
        return {
            "holding_amount": 1_000_000,
            "holding_cost": 1_050_000,
            "current_pnl": -50_000,
            "holding_days": 180,
            "max_drawdown": m["max_drawdown"],
            "weekly_drawdown": m["weekly_drawdown"],
            "daily_drawdown": m["daily_drawdown"],
            "yield_rate": m["yield_rate"],
            "drawdown_start_date": m.get("drawdown_start_date", ""),
            "drawdown_days": m.get("drawdown_days", 0),
            "data_date": m.get("data_date", as_of[:10]),
        }

    def fetch_info_package(self, product_code: str, as_of: str) -> dict[str, Any]:
        ds = self.cfg.get("data_sources") or {}
        static = self.fetch_static(product_code)
        performance = self.fetch_performance(product_code, as_of)
        degraded: list[str] = []
        if ds.get("evaluation_db") in (None, "none"):
            degraded.append("evaluation_db")
        if ds.get("product_reports") in (None, "none"):
            degraded.append("product_reports")
        notes = [
            "静态信息：统一产品库 product_library.yaml",
            "业绩指标：mock_product_metrics 模拟（无评价 API）",
        ]
        if "product_reports" in degraded:
            notes.append("未检索到该产品专项研报（知识库未接入）")
        return {
            "static": static,
            "performance": performance,
            "reports": None,
            "source_note": " · ".join(notes),
            "degraded": degraded,
            "data_source": {
                "product_static": ds.get("product_static", "product_library"),
                "product_performance": ds.get("product_performance", "mock"),
            },
        }
