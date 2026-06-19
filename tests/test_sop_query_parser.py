"""Tests for SOP query date parser."""

from datetime import date

from core.sop_query_parser import build_query_filters, parse_date_range


class TestSopQueryParser:
    def test_yesterday(self):
        ref = date(2026, 6, 19)
        since, until = parse_date_range("昨天的产品回撤事件有哪些", ref=ref)
        assert since == until == "2026-06-18"

    def test_today(self):
        ref = date(2026, 6, 19)
        since, until = parse_date_range("今天的回撤", ref=ref)
        assert since == until == "2026-06-19"

    def test_recent_days(self):
        ref = date(2026, 6, 19)
        since, until = parse_date_range("最近7天回撤", ref=ref)
        assert since == "2026-06-13"
        assert until == "2026-06-19"

    def test_build_filters_drawdown(self):
        f = build_query_filters("昨天回撤事件", ref=date(2026, 6, 19))
        assert f["since"] == f["until"] == "2026-06-18"
        assert f["drawdown_only"] is True
