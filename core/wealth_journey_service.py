"""财富盘点 → 资产诊断 — 场景化标签与模拟业绩数据。"""

from __future__ import annotations

import hashlib
from typing import Any

from core.allocation_config_service import AllocationConfigService
from core.config_loader import (
    INVESTMENT_CARD_KEYS,
    get_asset_type_aliases,
    get_demo_customer,
    get_product_map,
    get_risk_level_name,
    load_customer_profile,
    load_portfolio_mapping,
)
from core.data_store import get_customer_holdings

PLANNING_CATEGORY = "投资规划"

# 演示用模拟业绩（稳定、可复现）
_MOCK_PERFORMANCE: dict[str, dict[str, float]] = {
    "C20250602001": {
        "annual_return_pct": 12.5,
        "month_return_pct": 0.8,
        "principal_loss_pct": -5.5,
        "volatility_pct": 9.8,
    },
    "C20250602002": {
        "annual_return_pct": 3.8,
        "month_return_pct": 0.3,
        "principal_loss_pct": -1.2,
        "volatility_pct": 3.5,
    },
    "C20250602003": {
        "annual_return_pct": 28.6,
        "month_return_pct": 3.2,
        "principal_loss_pct": -9.5,
        "volatility_pct": 22.4,
    },
    "C20250602004": {
        "annual_return_pct": 4.1,
        "month_return_pct": -0.6,
        "principal_loss_pct": -4.8,
        "volatility_pct": 6.2,
    },
    "C20250602005": {
        "annual_return_pct": 11.2,
        "month_return_pct": 1.1,
        "principal_loss_pct": -7.8,
        "volatility_pct": 13.5,
    },
    "C20250602006": {
        "annual_return_pct": 9.5,
        "month_return_pct": 0.5,
        "principal_loss_pct": -3.0,
        "volatility_pct": 8.0,
    },
    "C20250602007": {
        "annual_return_pct": 5.2,
        "month_return_pct": -1.2,
        "principal_loss_pct": -3.5,
        "volatility_pct": 7.8,
    },
    "C20250602008": {
        "annual_return_pct": 18.3,
        "month_return_pct": 2.0,
        "principal_loss_pct": -6.2,
        "volatility_pct": 16.2,
    },
}

_FLAG_DEFS: dict[str, dict[str, str]] = {
    "four_money_mismatch": {
        "label": "四笔钱配置不合理",
        "severity": "warn",
    },
    "return_below_expected": {
        "label": "收益不达预期",
        "severity": "warn",
    },
    "return_above_expected": {
        "label": "收益超预期",
        "severity": "info",
    },
    "principal_loss_exceeded": {
        "label": "本金损失超阈值",
        "severity": "danger",
    },
    "volatility_exceeded": {
        "label": "波动率超预期",
        "severity": "danger",
    },
}


class WealthJourneyService:
    def __init__(self) -> None:
        self.config_svc = AllocationConfigService()
        self._risk_levels = {
            item["code"]: item
            for item in load_portfolio_mapping().get("customer_risk_levels", [])
        }

    def build_inventory(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for c in load_customer_profile().get("demo_customers", []):
            cid = c["customer_id"]
            row = self._build_customer_row(c)
            if row:
                rows.append(row)
        rows.sort(key=lambda r: (-len(r["flags"]), r["name"]))
        return rows

    def build_diagnosis(self, customer_id: str) -> dict[str, Any]:
        customer = get_demo_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer not found: {customer_id}")
        data = get_customer_holdings(customer_id)
        if not data:
            raise ValueError(f"No holdings: {customer_id}")

        row = self._build_customer_row(customer)
        if not row:
            raise ValueError(f"Unable to build diagnosis: {customer_id}")

        four_money = row["four_money"]
        flags = row["flags"]
        perf = row["performance"]
        model = row["model_benchmark"]
        loss_threshold = row["loss_threshold_pct"]

        conclusions: list[str] = []
        for f in flags:
            conclusions.append(f["hint"])

        if not flags:
            conclusions.append("当前各项指标与模型基准匹配良好，可维持现有配置并定期复盘。")

        mismatch_cats = [x for x in four_money if not x["in_band"]]
        if mismatch_cats:
            parts = "、".join(
                f"{x['category_name']}{'超配' if x['current_ratio'] > x['band'][1] else '低配'}"
                for x in mismatch_cats
            )
            conclusions.insert(0, f"资产配置结构诊断：{parts}，建议通过智能资配进行再平衡。")

        composite = self._composite_score(flags, four_money)
        dimensions = self._radar_dimensions(four_money, perf, model, loss_threshold, flags)

        return {
            "customer_id": customer_id,
            "name": customer["name"],
            "risk_profile": customer["risk_profile"],
            "risk_profile_name": get_risk_level_name(customer["risk_profile"]),
            "product_category": PLANNING_CATEGORY,
            "total_assets": row["total_assets"],
            "performance": perf,
            "model_benchmark": model,
            "loss_threshold_pct": loss_threshold,
            "four_money": four_money,
            "flags": flags,
            "conclusions": conclusions,
            "composite_score": composite,
            "beat_investors_pct": min(95, max(35, composite // 8 + 42)),
            "dimensions": dimensions,
            "diagnosis_date": "2025-12-26",
        }

    def _build_customer_row(self, customer: dict[str, Any]) -> dict[str, Any] | None:
        cid = customer["customer_id"]
        data = get_customer_holdings(cid)
        if not data:
            return None

        holdings = data["holdings"]
        idle = data["idle_cash"]
        risk = customer["risk_profile"]
        product_map = get_product_map()

        invest_holdings: dict[str, float] = {}
        for code, amount in holdings.items():
            prod = product_map.get(code)
            if prod and prod.get("asset_type") == "insurance":
                continue
            invest_holdings[code] = amount
        total = sum(invest_holdings.values()) + idle

        resolved = self.config_svc.resolve_profile_targets(PLANNING_CATEGORY, risk)
        model = resolved["model"]
        expect_ret = float(model.get("expect_annual_return") or 0)
        expect_vol = float(model.get("expect_volatility") or 0)

        inv_resolved = self.config_svc.resolve_asset_type_targets(PLANNING_CATEGORY, risk)
        inv_targets = inv_resolved["targets"]
        names = get_asset_type_aliases()
        current_by_type = {k: 0.0 for k in INVESTMENT_CARD_KEYS}
        for code, amount in invest_holdings.items():
            prod = product_map.get(code)
            if prod and prod.get("asset_type") in current_by_type:
                current_by_type[prod["asset_type"]] += amount

        four_money: list[dict[str, Any]] = []
        any_fm_oob = False
        for cat in INVESTMENT_CARD_KEYS:
            cfg = inv_targets[cat]
            cur = current_by_type.get(cat, 0.0)
            cur_ratio = cur / total if total else 0.0
            tgt_ratio = cfg["target"]
            band = cfg["band"]
            in_band = band[0] <= cur_ratio <= band[1]
            if not in_band:
                any_fm_oob = True
            four_money.append(
                {
                    "category": cat,
                    "category_name": names.get(cat, cat),
                    "current_amount": round(cur, 2),
                    "current_ratio": round(cur_ratio, 4),
                    "target_ratio": tgt_ratio,
                    "band": band,
                    "in_band": in_band,
                }
            )

        perf = self._performance(cid, risk, total, expect_ret, expect_vol)
        loss_threshold = self._loss_threshold(risk)
        flags = self._build_flags(
            any_fm_oob=any_fm_oob,
            perf=perf,
            expect_ret=expect_ret,
            expect_vol=expect_vol,
            loss_threshold=loss_threshold,
            risk_name=get_risk_level_name(risk),
            four_money=four_money,
        )

        month_amount = round(total * perf["month_return_pct"] / 100, 2)

        return {
            "customer_id": cid,
            "name": customer["name"],
            "risk_profile": risk,
            "risk_profile_name": get_risk_level_name(risk),
            "product_category": customer.get("product_category", PLANNING_CATEGORY),
            "total_assets": round(total, 2),
            "performance": {
                **perf,
                "month_return_amount": month_amount,
                "annual_return_amount": round(total * perf["annual_return_pct"] / 100, 2),
            },
            "model_benchmark": {
                "model_code": model.get("model_code", ""),
                "expect_annual_return_pct": expect_ret,
                "expect_volatility_pct": expect_vol,
            },
            "loss_threshold_pct": loss_threshold,
            "four_money": four_money,
            "flags": flags,
            "flag_count": len(flags),
        }

    def _performance(
        self,
        customer_id: str,
        risk_profile: str,
        total: float,
        expect_ret: float,
        expect_vol: float,
    ) -> dict[str, float]:
        if customer_id in _MOCK_PERFORMANCE:
            return dict(_MOCK_PERFORMANCE[customer_id])
        seed = int(hashlib.md5(customer_id.encode()).hexdigest()[:8], 16)
        annual = expect_ret + ((seed % 200) - 100) / 20.0
        month = ((seed >> 8) % 200 - 100) / 50.0
        vol = expect_vol + ((seed >> 16) % 100) / 10.0
        loss = -((seed >> 20) % 150) / 20.0
        return {
            "annual_return_pct": round(annual, 2),
            "month_return_pct": round(month, 2),
            "volatility_pct": round(max(0.5, vol), 2),
            "principal_loss_pct": round(loss, 2),
        }

    def _loss_threshold(self, risk_profile: str) -> float:
        level = self._risk_levels.get(risk_profile, {})
        return float(level.get("loss_pct") or 6)

    def _build_flags(
        self,
        *,
        any_fm_oob: bool,
        perf: dict[str, float],
        expect_ret: float,
        expect_vol: float,
        loss_threshold: float,
        risk_name: str,
        four_money: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        flags: list[dict[str, Any]] = []

        if any_fm_oob:
            oob_names = [
                x["category_name"]
                for x in four_money
                if not x["in_band"]
            ]
            flags.append(self._flag(
                "four_money_mismatch",
                f"该客户{risk_name}，资产配置存在超配/低配（{'、'.join(oob_names)}），建议介入调整。",
            ))

        annual = perf["annual_return_pct"]
        if annual < expect_ret - 0.5:
            flags.append(self._flag(
                "return_below_expected",
                f"该客户{risk_name}，模型预期年化收益 {expect_ret:.1f}%，实际 {annual:.1f}%，收益未达预期，建议优化持仓结构。",
            ))
        elif annual > expect_ret + 3:
            flags.append(self._flag(
                "return_above_expected",
                f"该客户{risk_name}，实际年化收益 {annual:.1f}% 明显高于模型预期 {expect_ret:.1f}%，可关注获利了结与再平衡。",
            ))

        loss = perf["principal_loss_pct"]
        if loss < -loss_threshold:
            flags.append(self._flag(
                "principal_loss_exceeded",
                f"该客户{risk_name}，当前本金浮亏 {abs(loss):.1f}% 超过可承受阈值 {loss_threshold:.0f}%，建议尽快介入调整。",
            ))

        vol = perf["volatility_pct"]
        if vol > expect_vol + 0.5:
            flags.append(self._flag(
                "volatility_exceeded",
                f"该客户{risk_name}，年化波动率 {vol:.1f}% 超出模型预期 {expect_vol:.1f}%，建议降低高风险敞口。",
            ))

        return flags

    def _flag(self, code: str, hint: str) -> dict[str, Any]:
        meta = _FLAG_DEFS[code]
        return {
            "code": code,
            "label": meta["label"],
            "severity": meta["severity"],
            "hint": hint,
        }

    def _composite_score(
        self,
        flags: list[dict[str, Any]],
        four_money: list[dict[str, Any]],
    ) -> int:
        score = 720
        score -= len(flags) * 45
        score -= sum(1 for x in four_money if not x["in_band"]) * 25
        for f in flags:
            if f["severity"] == "danger":
                score -= 30
            elif f["severity"] == "warn":
                score -= 15
        return max(320, min(780, score))

    def _radar_dimensions(
        self,
        four_money: list[dict[str, Any]],
        perf: dict[str, float],
        model: dict[str, Any],
        loss_threshold: float,
        flags: list[dict[str, Any]],
    ) -> dict[str, int]:
        in_band_ratio = sum(1 for x in four_money if x["in_band"]) / max(len(four_money), 1)
        assets = int(400 + in_band_ratio * 320)
        holdings = int(360 + in_band_ratio * 280)

        expect_ret = float(model.get("expect_annual_return_pct") or 0)
        ret_gap = perf["annual_return_pct"] - expect_ret
        returns = int(420 + min(280, max(-120, ret_gap * 15)))

        vol_gap = perf["volatility_pct"] - float(model.get("expect_volatility_pct") or 0)
        risk = int(480 - min(200, max(0, vol_gap * 12)))
        loss_penalty = 0
        if perf["principal_loss_pct"] < -loss_threshold:
            loss_penalty = int(abs(perf["principal_loss_pct"] + loss_threshold) * 8)
        risk = max(280, risk - loss_penalty)

        behavior = 520 - len(flags) * 35
        return {
            "assets": max(300, min(680, assets)),
            "holdings": max(300, min(680, holdings)),
            "returns": max(300, min(680, returns)),
            "risk": max(300, min(680, risk)),
            "behavior": max(300, min(680, behavior)),
        }
