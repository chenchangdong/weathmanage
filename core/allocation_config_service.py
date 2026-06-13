"""资产配置模型解析 — 客户风险 → 投资组合偏好 → 模型 → 四笔钱阈值。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.config_loader import (
    get_risk_level_name,
    load_four_money_mapping,
    load_four_money_rule,
    load_model_config,
    load_portfolio_mapping,
)

# DB 读写占位（保留注释备用）
# def load_model_config_from_db(): ...
# def load_portfolio_map_from_db(): ...


class AllocationConfigService:
    """五档客户风险 ↔ 五档投资组合偏好（1%/3%/6%/10%/15%）→ 模型 → 四笔钱阈值。"""

    RISK_CODES = ("conservative", "prudent", "balanced", "growth", "aggressive")

    def __init__(self) -> None:
        self._fm_mapping = load_four_money_mapping()
        self._model_config = load_model_config()
        self._portfolio_mapping = load_portfolio_mapping()
        self._code_map: Dict[str, str] = self._fm_mapping.get("category_code_map", {
            "need_spend": "spend",
            "keep_value": "preserve",
            "grow_asset": "grow",
            "secure_money": "protect",
        })
        self._fm_names = self._build_four_money_names()
        self._risk_level_index = self._build_risk_level_index()

    def reload(self) -> None:
        self.__init__()

    def _build_risk_level_index(self) -> Dict[str, Dict[str, Any]]:
        """code → {name, loss_pct, loss_key}"""
        levels = self._portfolio_mapping.get("customer_risk_levels", [])
        return {item["code"]: item for item in levels}

    def get_loss_key_for_risk(self, product_category: str, risk_label: str) -> str:
        """客户风险等级 → 投资组合偏好档位 key。"""
        risk_label = risk_label.strip().lower()
        defaults = self._portfolio_mapping.get("risk_loss_default", {})
        cat_defaults = defaults.get(product_category, {})
        loss_key = cat_defaults.get(risk_label)
        if loss_key:
            return loss_key
        # 从 customer_risk_levels 读取
        level = self._risk_level_index.get(risk_label)
        if level and level.get("loss_key"):
            return level["loss_key"]
        raise ValueError(f"未配置风险等级映射: {product_category} / {risk_label}")

    def list_customer_risk_levels(self) -> List[Dict[str, Any]]:
        return list(self._portfolio_mapping.get("customer_risk_levels", []))

    def _build_four_money_names(self) -> Dict[str, str]:
        rule = load_four_money_rule()
        cats = rule.get("categories", {})
        names: Dict[str, str] = {}
        for engine_code, info in cats.items():
            names[engine_code] = info.get("name", engine_code)
        return names

    def get_model_by_customer_risk(
        self,
        product_category: str,
        risk_label: str,
        loss_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        客户风险等级 → 投资组合偏好 → 资产配置模型。

        risk_label: conservative | prudent | balanced | growth | aggressive
        """
        portfolio_map = self._portfolio_mapping.get("portfolio_map", {})
        if product_category not in portfolio_map:
            raise ValueError(f"未知产品分类: {product_category}")

        risk_label = risk_label.strip().lower()
        if loss_key is None:
            loss_key = self.get_loss_key_for_risk(product_category, risk_label)

        cat_map = portfolio_map[product_category]
        if loss_key not in cat_map:
            raise ValueError(
                f"产品分类 {product_category} 下无偏好档位 {loss_key}，"
                f"请检查 portfolio_mapping.yaml"
            )

        entry = cat_map[loss_key]
        model_code = entry["target_model"]
        model_list = self._model_config.get("model_list", {})
        if model_code not in model_list:
            raise ValueError(f"模型编码不存在: {model_code}")

        model = model_list[model_code]
        level_info = self._risk_level_index.get(risk_label, {})
        return {
            "product_category": product_category,
            "risk_label": risk_label,
            "risk_name": level_info.get("name") or get_risk_level_name(risk_label),
            "loss_key": loss_key,
            "loss_pct": level_info.get("loss_pct"),
            "loss_label": entry.get("label", loss_key),
            "model_code": model_code,
            "model_name": model.get("model_name", model_code),
            "expect_annual_return": model.get("expect_annual_return"),
            "expect_volatility": model.get("expect_volatility"),
            "customer_risk": entry.get("customer_risk", risk_label),
        }

    def _asset_breakdown_entry(
        self,
        asset_type: str,
        limits: List[float],
        aliases: Dict[str, str],
    ) -> Dict[str, Any]:
        lo, mid, hi = limits
        return {
            "asset_type": asset_type,
            "alias": aliases.get(asset_type, asset_type),
            "lower_pct": lo,
            "benchmark_pct": mid,
            "upper_pct": hi,
        }

    def _aggregate_category_threshold(
        self,
        fm_key: str,
        rule: Dict[str, Any],
        asset_limits: Dict[str, List[float]],
        aliases: Dict[str, str],
    ) -> tuple[float, float, float, List[Dict[str, Any]]]:
        """将模型资产阈值聚合为单个大类阈值（%）。"""
        asset_types = rule.get("asset_type", [])
        asset_breakdown: List[Dict[str, Any]] = []
        for asset_type in asset_types:
            if asset_type not in asset_limits:
                continue
            asset_breakdown.append(
                self._asset_breakdown_entry(asset_type, asset_limits[asset_type], aliases)
            )

        aggregate_mode = rule.get("threshold_aggregate")
        if aggregate_mode == "grow_equity_alt":
            equity = asset_limits.get("equity", [0.0, 0.0, 0.0])
            alternative = asset_limits.get("alternative", [0.0, 0.0, 0.0])
            lower = equity[0]
            benchmark = equity[1] + alternative[1]
            upper = min(equity[2] + alternative[1], 100.0)
            return lower, benchmark, upper, asset_breakdown

        lower = benchmark = upper = 0.0
        for entry in asset_breakdown:
            lower += entry["lower_pct"]
            benchmark += entry["benchmark_pct"]
            upper += entry["upper_pct"]
        return lower, benchmark, upper, asset_breakdown

    def calc_four_money_benchmark_sum(self, asset_limits: Dict[str, List[float]]) -> float:
        """四笔钱各大类基准值之和（%）。"""
        fm_rules = self._fm_mapping.get("four_money_rule", {})
        aliases = self._fm_mapping.get("asset_alias", {})
        total = 0.0
        for fm_key, rule in fm_rules.items():
            _, benchmark, _, _ = self._aggregate_category_threshold(
                fm_key, rule, asset_limits, aliases
            )
            total += benchmark
        return round(total, 4)

    def validate_four_money_benchmark_sum(
        self,
        asset_limits: Dict[str, List[float]],
        *,
        model_label: str = "",
        tolerance: float = 0.01,
    ) -> None:
        total = self.calc_four_money_benchmark_sum(asset_limits)
        if abs(total - 100.0) > tolerance:
            prefix = f"模型「{model_label}」" if model_label else "该模型"
            raise ValueError(
                f"{prefix}四笔钱基准值之和为 {total:g}%，须等于 100%"
            )

    def calc_four_money_threshold(self, model_code: str) -> Dict[str, Any]:
        """按模型五类资产聚合为四笔钱阈值（%）。"""
        model_list = self._model_config.get("model_list", {})
        if model_code not in model_list:
            raise ValueError(f"模型编码不存在: {model_code}")

        model = model_list[model_code]
        asset_limits: Dict[str, List[float]] = model.get("asset_limit", {})
        fm_rules = self._fm_mapping.get("four_money_rule", {})
        aliases = self._fm_mapping.get("asset_alias", {})

        thresholds: Dict[str, Dict[str, Any]] = {}
        for fm_key, rule in fm_rules.items():
            engine_code = self._code_map.get(fm_key, fm_key)
            lower, benchmark, upper, asset_breakdown = self._aggregate_category_threshold(
                fm_key, rule, asset_limits, aliases
            )

            thresholds[engine_code] = {
                "four_money_key": fm_key,
                "category_name": self._fm_names.get(engine_code, engine_code),
                "lower_pct": round(lower, 4),
                "benchmark_pct": round(benchmark, 4),
                "upper_pct": round(upper, 4),
                "asset_breakdown": asset_breakdown,
            }

        return {
            "model_code": model_code,
            "model_name": model.get("model_name", model_code),
            "expect_annual_return": model.get("expect_annual_return"),
            "expect_volatility": model.get("expect_volatility"),
            "thresholds": thresholds,
        }

    def to_engine_profile_targets(
        self, thresholds: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for cat, t in thresholds.items():
            lo = t["lower_pct"] / 100.0
            mid = t["benchmark_pct"] / 100.0
            hi = t["upper_pct"] / 100.0
            result[cat] = {"target": mid, "band": [lo, hi]}
        return result

    def resolve_profile_targets(
        self,
        product_category: str,
        risk_label: str,
        loss_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """完整链路：客户等级 → 投资组合偏好 → 模型 → 四笔钱阈值。"""
        model_info = self.get_model_by_customer_risk(product_category, risk_label, loss_key)
        threshold_data = self.calc_four_money_threshold(model_info["model_code"])
        targets = self.to_engine_profile_targets(threshold_data["thresholds"])
        return {
            "model": model_info,
            "thresholds": threshold_data,
            "targets": targets,
        }

    def resolve_asset_type_targets(
        self,
        product_category: str,
        risk_label: str,
        loss_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """投资规划：模型五类资产阈值中的四类（不含保障类）。"""
        from core.config_loader import INVESTMENT_CARD_KEYS

        model_info = self.get_model_by_customer_risk(product_category, risk_label, loss_key)
        model_list = self._model_config.get("model_list", {})
        model = model_list.get(model_info["model_code"], {})
        limits: Dict[str, List[float]] = model.get("asset_limit", {})
        targets: Dict[str, Dict[str, Any]] = {}
        for asset_type in INVESTMENT_CARD_KEYS:
            lo, mid, hi = (limits.get(asset_type) or [0.0, 0.0, 0.0])[:3]
            targets[asset_type] = {
                "target": mid / 100.0,
                "band": [lo / 100.0, hi / 100.0],
            }
        return {
            "model": model_info,
            "targets": targets,
            "asset_limits": {k: limits.get(k, [0, 0, 0]) for k in INVESTMENT_CARD_KEYS},
        }

    def list_models(self) -> List[str]:
        return list(self._model_config.get("model_list", {}).keys())

    def find_model_portfolio_refs(self, model_code: str) -> List[Dict[str, Any]]:
        """查找风险映射中引用该模型的条目。"""
        refs: List[Dict[str, Any]] = []
        portfolio_map = self._portfolio_mapping.get("portfolio_map", {})
        for cat, loss_map in portfolio_map.items():
            if not isinstance(loss_map, dict):
                continue
            for loss_key, entry in loss_map.items():
                if isinstance(entry, dict) and entry.get("target_model") == model_code:
                    refs.append({
                        "product_category": cat,
                        "loss_key": loss_key,
                        "loss_label": entry.get("label", loss_key),
                        "customer_risk": entry.get("customer_risk", ""),
                    })
        return refs

    def get_model_detail(self, model_code: str) -> Dict[str, Any]:
        model_list = self._model_config.get("model_list", {})
        if model_code not in model_list:
            raise ValueError(f"模型不存在: {model_code}")
        return {
            "model_code": model_code,
            **model_list[model_code],
            "four_money_threshold": self.calc_four_money_threshold(model_code),
        }

    def get_portfolio_map_table(self, filter_category: Optional[str] = None) -> List[Dict[str, Any]]:
        portfolio_map = self._portfolio_mapping.get("portfolio_map", {})
        model_list = self._model_config.get("model_list", {})
        risk_options = [
            {"code": lv["code"], "name": lv["name"]}
            for lv in self.list_customer_risk_levels()
        ]
        rows: List[Dict[str, Any]] = []
        idx = 0
        categories = [filter_category] if filter_category else list(portfolio_map.keys())

        for cat in categories:
            if cat not in portfolio_map:
                continue
            for loss_key, entry in sorted(
                portfolio_map[cat].items(),
                key=lambda x: int(x[0].replace("loss_", "").replace("pct", "") or 0),
            ):
                idx += 1
                model_code = entry.get("target_model", "")
                model = model_list.get(model_code, {})
                rows.append({
                    "row_id": idx,
                    "product_category": cat,
                    "loss_key": loss_key,
                    "loss_label": entry.get("label", loss_key),
                    "target_model": model_code,
                    "ret": model.get("expect_annual_return"),
                    "vol": model.get("expect_volatility"),
                    "customer_risk": entry.get("customer_risk", ""),
                    "invest_term": entry.get("invest_term", "--"),
                    "model_options": list(model_list.keys()),
                    "risk_options": risk_options,
                })
        return rows
