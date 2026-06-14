"""财富健康标志驱动配仓 — 独立于一键 smart_one_click 的大类目标求解器。"""

from __future__ import annotations

from typing import Any

from core.config_loader import INVESTMENT_CARD_KEYS

CASH = "cash"
FIXED = "fixed_income"
EQUITY = "equity"
ALT = "alternative"

PERFORMANCE_FLAG_CODES = frozenset({
    "return_below_expected",
    "return_above_expected",
    "principal_loss_exceeded",
    "volatility_exceeded",
})

STRUCTURE_ONLY_FLAG = "four_money_mismatch"

EQUITY_BLEND_RATIO = 0.5  # 收益低 + 波动高 时权益折中系数

SELL_ORDER = {
    "return_below_expected": [CASH, FIXED, ALT],
    "return_above_expected": [EQUITY, ALT],
    "principal_loss_exceeded": [EQUITY, ALT],
    "volatility_exceeded": [EQUITY, ALT],
}

BUY_ORDER = {
    "return_below_expected": [EQUITY, ALT],
    "return_above_expected": [CASH, FIXED],
    "principal_loss_exceeded": [FIXED, CASH],
    "volatility_exceeded": [CASH, FIXED],
}

PASSIVE_BUY_ORDER = [FIXED, CASH, ALT, EQUITY]
PASSIVE_SELL_ORDER = [ALT, EQUITY, FIXED, CASH]

_EPS = 0.01


class FlagDrivenSolverError(ValueError):
    """无有效业绩/风险标志，不应执行个性化配仓。"""


class FlagDrivenSolver:
    """根据财富健康标志计算四类资产目标金额（含归一化）。"""

    def solve(
        self,
        *,
        current_cat: dict[str, float],
        idle_cash: float,
        profile_targets: dict[str, Any],
        flag_codes: list[str],
    ) -> tuple[dict[str, float], list[str]]:
        effective = self._effective_flags(flag_codes)
        if not effective:
            raise FlagDrivenSolverError("财富健康，请用全账户一键配仓")

        total = sum(current_cat.get(c, 0.0) for c in INVESTMENT_CARD_KEYS) + idle_cash
        if total <= 0:
            raise ValueError("Total assets must be positive")

        cur = self._cash_pool(current_cat, idle_cash)
        bounds = self._bounds(profile_targets, total)

        intent, passive, normalize_key = self._merged_intents(
            effective, cur, total, bounds, profile_targets
        )
        intent = self._alternative_yields_equity(intent, cur, bounds)
        tgt = {c: round(intent[c], 2) for c in INVESTMENT_CARD_KEYS}

        notes: list[str] = []
        notes.append(f"个性化配仓依据：{self._flag_labels(effective)}")
        if (
            "return_above_expected" in effective
            and "volatility_exceeded" in effective
        ):
            notes.append("兼考虑收益偏高，权益已收到基准止盈")

        diff = round(total - sum(tgt.values()), 2)
        if abs(diff) > _EPS:
            tgt, norm_notes, residual = self._normalize(
                tgt=tgt,
                diff=diff,
                total=total,
                bounds=bounds,
                dominant=normalize_key,
                passive=passive,
            )
            notes.extend(norm_notes)
            if abs(residual) > _EPS:
                tgt, spill_note = self._spill_residual(
                    tgt, residual, total, bounds
                )
                notes.append(spill_note)
                notes.append(
                    "模型区间内无法完全满足标志配仓意图，已取次优解"
                )

        final_sum = round(sum(tgt.values()), 2)
        if abs(final_sum - total) > _EPS:
            notes.append(
                f"大类目标合计{final_sum:,.0f}元与总资产{total:,.0f}元存在"
                f"{total - final_sum:+,.0f}元差额，请结合产品触顶情况人工复核"
            )

        return tgt, notes

    @staticmethod
    def _effective_flags(flag_codes: list[str]) -> set[str]:
        return {c for c in flag_codes if c in PERFORMANCE_FLAG_CODES}

    @staticmethod
    def _cash_pool(current_cat: dict[str, float], idle_cash: float) -> dict[str, float]:
        pool = {c: current_cat.get(c, 0.0) for c in INVESTMENT_CARD_KEYS}
        pool[CASH] += idle_cash
        return pool

    @staticmethod
    def _bounds(profile_targets: dict[str, Any], total: float) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for cat in INVESTMENT_CARD_KEYS:
            cfg = profile_targets[cat]
            bench = cfg["target"]
            lo, hi = cfg["band"]
            floor = max(bench, lo) if cat == CASH else lo
            out[cat] = {
                "bench_ratio": bench,
                "lo_ratio": lo,
                "hi_ratio": hi,
                "floor_ratio": floor,
                "bench": bench * total,
                "lo": lo * total,
                "hi": hi * total,
                "floor": floor * total,
            }
        return out

    @staticmethod
    def _dominant_scenario(codes: set[str]) -> str:
        """复合场景主导优先级：本金亏 > 波动高 > 收益高 > 收益低。"""
        if "principal_loss_exceeded" in codes:
            return "principal_loss_exceeded"
        if "volatility_exceeded" in codes:
            return "volatility_exceeded"
        if "return_above_expected" in codes:
            return "return_above_expected"
        if "return_below_expected" in codes:
            return "return_below_expected"
        return "volatility_exceeded"

    def _merged_intents(
        self,
        codes: set[str],
        cur: dict[str, float],
        total: float,
        bounds: dict[str, dict[str, float]],
        profile_targets: dict[str, Any],
    ) -> tuple[dict[str, float], set[str], str]:
        passive: set[str] = set()

        if "return_above_expected" in codes and "principal_loss_exceeded" in codes:
            intents, passive = self._scenario_intents(
                "principal_loss_exceeded", cur, total, bounds, passive
            )
            return intents, passive, "principal_loss_exceeded"

        if "return_below_expected" in codes and "principal_loss_exceeded" in codes:
            intents, passive = self._scenario_intents(
                "principal_loss_exceeded", cur, total, bounds, passive
            )
            return intents, passive, "principal_loss_exceeded"

        if "return_below_expected" in codes and "volatility_exceeded" in codes:
            intents, passive = self._merge_below_vol(cur, total, bounds, passive)
            return intents, passive, "return_below_expected"

        if "principal_loss_exceeded" in codes and "volatility_exceeded" in codes:
            s3, p3 = self._scenario_intents(
                "principal_loss_exceeded", cur, total, bounds, set()
            )
            s4, _ = self._scenario_intents(
                "volatility_exceeded", cur, total, bounds, set()
            )
            merged = dict(s3)
            for cat in (EQUITY, ALT):
                merged[cat] = min(s3[cat], s4[cat])
            passive = p3 | {c for c in INVESTMENT_CARD_KEYS if merged[c] == cur[c]}
            return merged, passive, "principal_loss_exceeded"

        if "return_above_expected" in codes and "volatility_exceeded" in codes:
            intents, passive = self._scenario_intents(
                "volatility_exceeded", cur, total, bounds, passive
            )
            return intents, passive, "volatility_exceeded"

        if len(codes) == 1:
            code = next(iter(codes))
            intents, passive = self._scenario_intents(code, cur, total, bounds, passive)
            return intents, passive, code

        primary = self._dominant_scenario(codes)
        intents, passive = self._scenario_intents(primary, cur, total, bounds, passive)
        return intents, passive, primary

    def _merge_below_vol(
        self,
        cur: dict[str, float],
        total: float,
        bounds: dict[str, dict[str, float]],
        passive: set[str],
    ) -> tuple[dict[str, float], set[str]]:
        intents, p4passive = self._scenario_intents(
            "volatility_exceeded", cur, total, bounds, passive
        )

        b = bounds[EQUITY]
        compromise = (
            b["bench"]
            + (b["hi"] - b["bench"]) * EQUITY_BLEND_RATIO
        )
        intents[EQUITY] = self._clamp(compromise, b["floor"], b["hi"])

        for cat in INVESTMENT_CARD_KEYS:
            if abs(intents[cat] - cur[cat]) < _EPS:
                passive.add(cat)

        return intents, passive | p4passive

    def _scenario_intents(
        self,
        scenario: str,
        cur: dict[str, float],
        total: float,
        bounds: dict[str, dict[str, float]],
        passive: set[str],
    ) -> tuple[dict[str, float], set[str]]:
        intents: dict[str, float] = {}

        if scenario == "return_below_expected":
            intents[CASH] = self._to_bench_down(cur[CASH], bounds[CASH])
            intents[FIXED] = self._to_upper_cap(cur[FIXED], bounds[FIXED])
            # 至少基准，不主动减超基准仓；Normalize 按 BUY 顺序加至上限
            intents[EQUITY] = self._to_bench_up(cur[EQUITY], bounds[EQUITY])
            intents[ALT] = self._hold_in_band(cur[ALT], bounds[ALT])

        elif scenario == "return_above_expected":
            intents[CASH] = self._to_bench_up(cur[CASH], bounds[CASH])
            # 至少基准，不主动减超基准仓；Normalize 按 BUY 顺序加至上限
            intents[FIXED] = self._to_bench_up(cur[FIXED], bounds[FIXED])
            intents[EQUITY] = self._to_bench_down(cur[EQUITY], bounds[EQUITY])
            intents[ALT] = bounds[ALT]["lo"]

        elif scenario == "principal_loss_exceeded":
            intents[CASH] = self._to_bench_up(cur[CASH], bounds[CASH])
            intents[FIXED] = bounds[FIXED]["hi"]
            intents[EQUITY] = bounds[EQUITY]["lo"]
            intents[ALT] = self._to_bench_down(cur[ALT], bounds[ALT])

        elif scenario == "volatility_exceeded":
            intents[CASH] = self._to_bench_up(cur[CASH], bounds[CASH])
            intents[FIXED] = self._to_bench_up(cur[FIXED], bounds[FIXED])
            intents[EQUITY] = self._to_bench_down(cur[EQUITY], bounds[EQUITY])
            intents[ALT] = self._to_bench_down(cur[ALT], bounds[ALT])

        else:
            raise ValueError(f"Unknown scenario: {scenario}")

        for cat in INVESTMENT_CARD_KEYS:
            intents[cat] = self._clamp(
                intents[cat], bounds[cat]["floor"], bounds[cat]["hi"]
            )
            if abs(intents[cat] - cur[cat]) < _EPS:
                passive.add(cat)

        return intents, passive

    def _alternative_yields_equity(
        self,
        intent: dict[str, float],
        cur: dict[str, float],
        bounds: dict[str, dict[str, float]],
    ) -> dict[str, float]:
        out = dict(intent)
        eq_target = out[EQUITY]
        eq_headroom = bounds[EQUITY]["hi"] - cur[EQUITY]
        need = max(0.0, eq_target - cur[EQUITY])

        if need <= _EPS:
            return out

        alt_release = min(
            need,
            max(0.0, out[ALT] - bounds[ALT]["floor"]),
            max(0.0, cur[ALT] - bounds[ALT]["floor"]),
        )
        if alt_release > _EPS:
            out[ALT] = max(bounds[ALT]["floor"], out[ALT] - alt_release)
            boost = min(alt_release, bounds[EQUITY]["hi"] - out[EQUITY])
            out[EQUITY] = min(bounds[EQUITY]["hi"], out[EQUITY] + boost)

        if out[EQUITY] < bounds[EQUITY]["hi"] - _EPS:
            out[ALT] = min(out[ALT], self._hold_in_band(cur[ALT], bounds[ALT]))

        return out

    def _normalize(
        self,
        *,
        tgt: dict[str, float],
        diff: float,
        total: float,
        bounds: dict[str, dict[str, float]],
        dominant: str,
        passive: set[str],
    ) -> tuple[dict[str, float], list[str], float]:
        notes: list[str] = []
        out = dict(tgt)
        remaining = diff

        if remaining > _EPS:
            order = BUY_ORDER[dominant]
            for cat in order:
                if remaining <= _EPS:
                    break
                cap = bounds[cat]["hi"] - out[cat]
                if cap <= _EPS:
                    continue
                add = min(remaining, cap)
                out[cat] = round(out[cat] + add, 2)
                remaining = round(remaining - add, 2)
                notes.append(f"主动增配{self._cat_label(cat)}{add:,.0f}元以凑平总资产")

        elif remaining < -_EPS:
            order = SELL_ORDER[dominant]
            need = -remaining
            for cat in order:
                if need <= _EPS:
                    break
                cap = out[cat] - bounds[cat]["floor"]
                if cap <= _EPS:
                    continue
                cut = min(need, cap)
                out[cat] = round(out[cat] - cut, 2)
                need = round(need - cut, 2)
                remaining = round(remaining + cut, 2)
                notes.append(f"主动减配{self._cat_label(cat)}{cut:,.0f}元以凑平总资产")

        if abs(remaining) > _EPS:
            out, remaining, passive_notes = self._passive_absorb(
                out, remaining, bounds, passive
            )
            notes.extend(passive_notes)

        return out, notes, remaining

    def _passive_absorb(
        self,
        tgt: dict[str, float],
        diff: float,
        bounds: dict[str, dict[str, float]],
        passive: set[str],
    ) -> tuple[dict[str, float], float, list[str]]:
        notes: list[str] = []
        out = dict(tgt)
        remaining = diff
        pool = [c for c in (PASSIVE_BUY_ORDER if remaining > 0 else PASSIVE_SELL_ORDER)]

        for cat in pool:
            if abs(remaining) <= _EPS:
                break
            if remaining > _EPS:
                cap = bounds[cat]["hi"] - out[cat]
                if cap <= _EPS:
                    continue
                add = min(remaining, cap)
                out[cat] = round(out[cat] + add, 2)
                remaining = round(remaining - add, 2)
                tag = "被动" if cat in passive else "余量"
                notes.append(f"{tag}吸收：增配{self._cat_label(cat)}{add:,.0f}元")
            else:
                need = -remaining
                cap = out[cat] - bounds[cat]["floor"]
                if cap <= _EPS:
                    continue
                cut = min(need, cap)
                out[cat] = round(out[cat] - cut, 2)
                remaining = round(remaining + cut, 2)
                tag = "被动" if cat in passive else "余量"
                notes.append(f"{tag}吸收：减配{self._cat_label(cat)}{cut:,.0f}元")

        return out, remaining, notes

    def _spill_residual(
        self,
        tgt: dict[str, float],
        residual: float,
        total: float,
        bounds: dict[str, dict[str, float]],
    ) -> tuple[dict[str, float], str]:
        out = dict(tgt)
        cat = FIXED
        if residual > 0:
            add = min(residual, bounds[cat]["hi"] - out[cat])
            out[cat] = round(out[cat] + add, 2)
            return out, f"残差{add:,.0f}元归入{self._cat_label(cat)}（band 最宽）"
        need = -residual
        cut = min(need, out[cat] - bounds[cat]["floor"])
        out[cat] = round(out[cat] - cut, 2)
        return out, f"残差{cut:,.0f}元由{self._cat_label(cat)}吸收"

    @staticmethod
    def _to_bench_up(cur: float, b: dict[str, float]) -> float:
        if cur < b["bench"] - _EPS:
            return b["bench"]
        return cur

    @staticmethod
    def _to_bench_down(cur: float, b: dict[str, float]) -> float:
        if cur > b["bench"] + _EPS:
            return b["bench"]
        return cur

    @staticmethod
    def _to_upper_cap(cur: float, b: dict[str, float]) -> float:
        if cur > b["hi"] + _EPS:
            return b["hi"]
        return cur

    @staticmethod
    def _hold_in_band(cur: float, b: dict[str, float]) -> float:
        return FlagDrivenSolver._clamp(cur, b["floor"], b["hi"])

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _cat_label(cat: str) -> str:
        labels = {
            CASH: "现金类",
            FIXED: "固收类",
            EQUITY: "权益类",
            ALT: "另类及其他",
        }
        return labels.get(cat, cat)

    @staticmethod
    def _flag_labels(codes: set[str]) -> str:
        labels = {
            "return_below_expected": "收益不达预期",
            "return_above_expected": "收益超预期",
            "principal_loss_exceeded": "本金损失超阈值",
            "volatility_exceeded": "波动率超预期",
        }
        return "、".join(labels.get(c, c) for c in sorted(codes))
