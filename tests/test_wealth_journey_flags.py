"""财富健康标志与最新演示持仓、模拟业绩对齐。"""

from __future__ import annotations

from core.config_loader import load_customer_profile
from core.wealth_journey_service import WealthJourneyService

# 有效标志（个性化配仓/API 过滤 four_money_mismatch 后）
EXPECTED_EFFECTIVE_FLAGS: dict[str, list[str]] = {
    "C20250602001": ["return_above_expected"],
    "C20250602002": [],
    "C20250602003": ["volatility_exceeded"],
    "C20250602004": ["return_below_expected"],
    "C20250602005": ["return_above_expected"],
    "C20250602006": ["return_above_expected", "principal_loss_exceeded"],
    "C20250602007": ["principal_loss_exceeded"],
    "C20250602008": ["return_above_expected", "volatility_exceeded"],
}


class TestWealthJourneyFlags:
    def test_effective_flags_match_latest_holdings(self):
        svc = WealthJourneyService()
        for c in load_customer_profile()["demo_customers"]:
            cid = c["customer_id"]
            diagnosis = svc.build_diagnosis(cid)
            effective = [
                f["code"]
                for f in diagnosis["flags"]
                if f["code"] != "four_money_mismatch"
            ]
            assert effective == EXPECTED_EFFECTIVE_FLAGS[cid], (
                f"{c['name']}({cid}): got {effective}, "
                f"expected {EXPECTED_EFFECTIVE_FLAGS[cid]}"
            )

    def test_zhou_has_no_demand_deposit_holding(self):
        from core.data_store import get_customer_holdings

        holdings = get_customer_holdings("C20250602007")["holdings"]
        assert holdings.get("P000", 0) < 0.01

    def test_li_is_healthy(self):
        svc = WealthJourneyService()
        diagnosis = svc.build_diagnosis("C20250602002")
        assert diagnosis["flags"] == []
