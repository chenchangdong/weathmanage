"""财富健康标志与最新演示持仓、SOP 跑批对齐。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config_loader import load_customer_profile
from core.sop_event_store import SopEventStore
from core.wealth_journey_service import WealthJourneyService

_FIXTURE_EVENTS = Path(__file__).resolve().parent / "fixtures" / "sop_events_demo.json"


@pytest.fixture(autouse=True)
def _demo_sop_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """演示 SOP 事件与持仓对齐，不依赖本地 data/sop_events.json 跑批结果。"""
    store = SopEventStore(path=_FIXTURE_EVENTS)
    monkeypatch.setattr(
        "core.sop_wealth_flags.SopEventStore",
        lambda path=None: store if path is None else SopEventStore(path=path),
    )

# 有效标志（个性化配仓/API 过滤 four_money_mismatch 后）
# 回撤/收益不达预期由 SOP 跑批驱动；本金损失/波动率仍为模拟业绩
EXPECTED_EFFECTIVE_FLAGS: dict[str, list[str]] = {
    "C20250602001": ["return_above_expected"],
    "C20250602002": ["max_drawdown_exceeded"],
    "C20250602003": ["max_drawdown_exceeded", "volatility_exceeded"],
    "C20250602004": ["return_below_expected"],
    "C20250602005": [],
    "C20250602006": ["principal_loss_exceeded"],
    "C20250602007": ["principal_loss_exceeded"],
    "C20250602008": ["volatility_exceeded"],
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
        assert holdings.get("000", 0) < 0.01

    def test_li_has_drawdown_flag_from_sop(self):
        svc = WealthJourneyService()
        diagnosis = svc.build_diagnosis("C20250602002")
        assert len(diagnosis["flags"]) == 1
        f = diagnosis["flags"][0]
        assert f["code"] == "max_drawdown_exceeded"
        assert f.get("source") == "sop"
        assert f.get("sop_events")

    def test_personalized_block_message_structure_only(self):
        from core.wealth_journey_service import personalized_allocation_block_message

        msg = personalized_allocation_block_message([
            {"code": "four_money_mismatch", "label": "四笔钱配置不合理"},
        ])
        assert msg and "四笔钱" in msg

    def test_personalized_block_message_healthy(self):
        from core.wealth_journey_service import personalized_allocation_block_message

        msg = personalized_allocation_block_message([])
        assert msg and "财富健康" in msg

    def test_sop_driven_flags_have_source(self):
        svc = WealthJourneyService()
        for cid in ("C20250602002", "C20250602003", "C20250602004"):
            flags = svc.build_diagnosis(cid)["flags"]
            sop_codes = {"max_drawdown_exceeded", "return_below_expected"}
            for f in flags:
                if f["code"] in sop_codes:
                    assert f.get("source") == "sop"
                    assert f.get("sop_events")

    def test_score_context_in_diagnosis(self):
        svc = WealthJourneyService()
        healthy = svc.build_diagnosis("C20250602005")
        ctx = healthy["score_context"]
        assert ctx["health_level"] == "healthy"
        assert ctx["flag_count"] == 0
        assert ctx["allocation_hint"] and "财富健康" in ctx["allocation_hint"]

        li = svc.build_diagnosis("C20250602002")
        ctx_li = li["score_context"]
        assert ctx_li["health_level"] == "attention"
        assert ctx_li["flag_count"] == 1
        assert ctx_li["sop_flag_count"] == 1
        assert str(li["composite_score"]) in ctx_li["summary"]

    def test_allocation_structure_diagnosis_merges_flags(self):
        svc = WealthJourneyService()
        li = svc.build_diagnosis("C20250602002")
        assert len(li["conclusions"]) == 1
        script = li["conclusions"][0]
        assert script.startswith("资产配置结构诊断：")
        assert li["flags"][0]["label"] in script or "回撤" in script

        healthy = svc.build_diagnosis("C20250602005")
        assert len(healthy["conclusions"]) == 1
        assert "匹配良好" in healthy["conclusions"][0]

        multi = svc.build_diagnosis("C20250602003")
        assert len(multi["conclusions"]) == 1
        assert multi["conclusions"][0].startswith("资产配置结构诊断：")
