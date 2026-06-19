"""SOP 跑批与财富盘点标志打通。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.sop_event_store import SopEventStore
from core.sop_wealth_flags import resolve_sop_wealth_flags


@pytest.fixture
def temp_event_store(tmp_path: Path) -> SopEventStore:
    path = tmp_path / "sop_events.json"
    path.write_text(
        json.dumps(
            {
                "next_event_seq": 10,
                "rule_logs": [],
                "composite_events": [
                    {
                        "event_id": "EVT01",
                        "composite_code": "EVT_DRAWDOWN",
                        "scenario": "最大回撤超阈值",
                        "product_code": "T305",
                        "product_name": "test-顶点-灵活T3",
                        "drawdown_detail": "近60日最大回撤达 -3.6%，超阈值 -3%",
                        "data_date": "2026-06-19",
                    },
                    {
                        "event_id": "EVT02",
                        "composite_code": "EVT_YIELD",
                        "scenario": "收益不达预期",
                        "product_code": "prd-ms-B5",
                        "product_name": "磐石3.0（演示产品）",
                        "drawdown_detail": "收益率低于 2%",
                        "data_date": "2026-06-19",
                    },
                    {
                        "event_id": "EVT03",
                        "composite_code": "EVT_DRAWDOWN",
                        "scenario": "最大回撤超阈值",
                        "product_code": "P999",
                        "product_name": "未持有产品",
                        "drawdown_detail": "不应匹配",
                        "data_date": "2026-06-20",
                    },
                ],
                "agent_outputs": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return SopEventStore(path=path)


class TestSopWealthFlags:
    def test_match_drawdown_for_held_product(self, temp_event_store: SopEventStore):
        flags = resolve_sop_wealth_flags(
            {"T305": 50000.0, "001": 1000.0},
            risk_name="稳健型",
            event_store=temp_event_store,
        )
        codes = [f["code"] for f in flags]
        assert codes == ["max_drawdown_exceeded"]
        assert "T305" in flags[0]["sop_events"][0]["product_code"]

    def test_match_yield_for_held_product(self, temp_event_store: SopEventStore):
        flags = resolve_sop_wealth_flags(
            {"prd-ms-B5": 120000.0},
            risk_name="平衡型",
            event_store=temp_event_store,
        )
        assert [f["code"] for f in flags] == ["return_below_expected"]

    def test_ignore_unheld_product_events(self, temp_event_store: SopEventStore):
        flags = resolve_sop_wealth_flags(
            {"001": 1000.0},
            risk_name="稳健型",
            event_store=temp_event_store,
        )
        assert flags == []

    def test_zero_amount_holding_ignored(self, temp_event_store: SopEventStore):
        flags = resolve_sop_wealth_flags(
            {"T305": 0.0},
            risk_name="稳健型",
            event_store=temp_event_store,
        )
        assert flags == []

    def test_only_latest_data_date_counts(self, tmp_path: Path):
        path = tmp_path / "sop_events.json"
        path.write_text(
            json.dumps(
                {
                    "next_event_seq": 10,
                    "rule_logs": [],
                    "composite_events": [
                        {
                            "event_id": "EVT01",
                            "composite_code": "EVT_DRAWDOWN",
                            "product_code": "T305",
                            "product_name": "旧批次",
                            "data_date": "2026-06-18",
                        },
                        {
                            "event_id": "EVT02",
                            "composite_code": "EVT_YIELD",
                            "product_code": "P999",
                            "product_name": "不应出现",
                            "data_date": "2026-06-19",
                        },
                    ],
                    "agent_outputs": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        store = SopEventStore(path=path)
        flags = resolve_sop_wealth_flags(
            {"T305": 50000.0},
            risk_name="稳健型",
            event_store=store,
        )
        assert flags == []
