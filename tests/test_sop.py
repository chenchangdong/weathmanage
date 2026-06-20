"""SOP 6.1 / 6.2 unit tests."""

from datetime import date
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from core.sop_event_store import SopEventStore
from core.sop_rule_engine import SopRuleEngine, evaluate_expression, mock_product_metrics
from main import app

client = TestClient(app)


def _alert_product_for(as_of: date, *, drawdown: Optional[bool] = None) -> str:
    """返回在指定日期 mock 会触发规则的产品代码（测试用）。"""
    engine = SopRuleEngine()
    rules = [r for r in engine.list_rules() if r.get("enabled", True)]
    if drawdown is True:
        rules = [r for r in rules if "回撤" in (r.get("name") or "")]
    elif drawdown is False:
        rules = [r for r in rules if "收益" in (r.get("name") or "")]
    for i in range(500):
        code = f"TST{i:04d}"
        metrics = mock_product_metrics(code, as_of)
        if any(engine.evaluate_rule(r, metrics) for r in rules):
            return code
    kind = "drawdown" if drawdown else "any"
    raise AssertionError(f"no {kind} alert product for {as_of}")


class TestSopRuleEngine:
    def test_evaluate_expression(self):
        metrics = {"max_drawdown": 6.5, "yield_rate": 1.5}
        assert evaluate_expression("max_drawdown > 5", metrics) is True
        assert evaluate_expression("yield_rate < 2", metrics) is True
        assert evaluate_expression("max_drawdown > 10", metrics) is False

    def test_mock_product_metrics_deterministic(self):
        d = date(2026, 6, 2)
        a = mock_product_metrics("PROD001", d)
        b = mock_product_metrics("PROD001", d)
        assert a == b
        assert "max_drawdown" in a

    def test_mock_product_metrics_varies_by_date(self):
        a = mock_product_metrics("PROD001", date(2026, 6, 2))
        b = mock_product_metrics("PROD001", date(2026, 6, 3))
        assert a["data_date"] != b["data_date"]
        assert a["max_drawdown"] != b["max_drawdown"]

    def test_mock_metrics_includes_category_and_asset_type(self):
        d = date(2026, 6, 2)
        m = mock_product_metrics("C201", d)
        assert m["category"] == "mod"
        assert m["category_label"] == "平衡型"
        assert m["asset_type"] == "equity"
        assert m["asset_type_label"] == "权益类"
        assert m["strategy_type"] == ""

        unset = mock_product_metrics("prd-ms-B5", d)
        assert unset["category"] == "mod"
        assert not unset.get("asset_type")

    def test_run_batch_event_includes_product_dimensions(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        d = date(2026, 6, 2)
        result = engine.run_batch(as_of=d, product_codes=["C201"], auto_cleanup=False)
        if not result["composite_events"]:
            pytest.skip("C201 did not trigger composite event on this date")
        evt = store.list_composite_events()[0]
        assert evt.get("category") == "mod"
        assert evt.get("asset_type") == "equity"
        assert evt.get("category_label") == "平衡型"

    def test_mock_mostly_normal(self):
        d = date(2026, 6, 2)
        engine = SopRuleEngine()
        rules = [r for r in engine.list_rules() if r.get("enabled", True)]
        alert_products = 0
        for i in range(50):
            code = f"PROD{i:03d}"
            m = mock_product_metrics(code, d)
            if any(engine.evaluate_rule(r, m) for r in rules):
                alert_products += 1
        assert alert_products <= 12

    def test_format_yield_event_detail(self):
        hit = {
            "rule_code": "YIELD_LOW_2",
            "business_type": "产品收益预警",
        }
        metrics = {"yield_rate": 1.21, "max_drawdown": 1.5}
        detail = SopRuleEngine._format_event_detail(
            hit, metrics, composite_code="EVT_YIELD"
        )
        assert "收益率" in detail
        assert "1.21" in detail
        assert "回撤" not in detail

    def test_run_batch_yield_event_detail(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        d = date(2026, 6, 2)
        code = _alert_product_for(d, drawdown=False)
        engine.run_batch(as_of=d, product_codes=[code], auto_cleanup=False)
        yield_events = [
            e for e in store.list_composite_events()
            if e.get("composite_code") == "EVT_YIELD"
        ]
        assert yield_events
        detail = yield_events[0].get("drawdown_detail") or ""
        assert "收益率" in detail
        assert "回撤" not in detail

    def test_run_batch_creates_logs(self, tmp_path, monkeypatch):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        result = engine.run_batch(as_of=date(2026, 6, 2), product_codes=[_alert_product_for(date(2026, 6, 2))])
        assert result["products_scanned"] == 1
        logs = store.list_rule_logs()
        assert isinstance(logs, list)

    def test_run_batch_idempotent(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        d = date(2026, 6, 2)
        code = _alert_product_for(d)
        first = engine.run_batch(as_of=d, product_codes=[code], auto_cleanup=False)
        second = engine.run_batch(as_of=d, product_codes=[code], auto_cleanup=False)
        assert second["composite_events"] == 0
        assert second["skipped_composite_events"] == first["composite_events"]
        assert len(store.list_composite_events()) == first["composite_events"]

    def test_run_batch_replace(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        d = date(2026, 6, 2)
        code = _alert_product_for(d)
        engine.run_batch(as_of=d, product_codes=[code], auto_cleanup=False)
        n1 = len(store.list_composite_events())
        engine.run_batch(
            as_of=d, product_codes=[code], replace=True, auto_cleanup=False
        )
        n2 = len(store.list_composite_events())
        assert n2 == n1

    def test_cleanup_retention(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        d_old = date(2026, 1, 1)
        code = _alert_product_for(d_old)
        engine.run_batch(as_of=d_old, product_codes=[code], auto_cleanup=False)
        assert store.list_composite_events()
        removed = store.cleanup_before(date(2026, 2, 1))
        assert removed["composite_events"] >= 1
        assert not store.list_composite_events()

    def test_dedupe_all(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        store.append_composite_events([
            {"event_id": "EVT01", "product_code": "P1", "composite_code": "EVT_DRAWDOWN", "data_date": "2026-06-02"},
            {"event_id": "EVT02", "product_code": "P1", "composite_code": "EVT_DRAWDOWN", "data_date": "2026-06-02"},
        ])
        removed = store.dedupe_all()
        assert removed["composite_events"] == 1
        assert len(store.list_composite_events()) == 1

    def test_purge_all(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        store.append_composite_events([
            {"event_id": "EVT01", "product_code": "P1", "composite_code": "EVT_DRAWDOWN", "data_date": "2026-06-02"},
        ])
        removed = store.purge_all()
        assert removed["composite_events"] == 1
        assert not store.list_composite_events()

    def test_stats_data_date_range(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        store.append_composite_events([
            {"event_id": "E1", "data_date": "2026-06-18"},
            {"event_id": "E2", "data_date": "2026-06-20"},
        ])
        s = store.stats()
        assert s["data_date_min"] == "2026-06-18"
        assert s["data_date_max"] == "2026-06-20"
        assert s["latest_data_date"] == "2026-06-20"

    def test_save_agent_output_status_label(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        store.append_composite_events([
            {"event_id": "E1", "data_date": "2026-06-18", "status_label": "待生成"},
        ])
        store.save_agent_output("E1", {"agent_status": "done", "event_description": "x"})
        evt = store.list_composite_events()[0]
        assert evt["status_label"] == "已生成"
        assert evt["agent_status"] == "done"

    def test_save_push_result_status_label(self, tmp_path):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        store.append_composite_events([
            {"event_id": "E1", "data_date": "2026-06-18", "agent_status": "done"},
        ])
        store.save_push_result("E1", "sent", [{"status": "sent"}])
        evt = store.list_composite_events()[0]
        assert evt["status_label"] == "已推送"
        assert evt["push_status"] == "sent"

    def test_query_yesterday_filter(self, tmp_path):
        from core.sop_query_parser import build_query_filters

        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        d_y = date(2026, 6, 18)
        d_t = date(2026, 6, 19)
        code_y = _alert_product_for(d_y, drawdown=True)
        engine.run_batch(as_of=d_y, product_codes=[code_y], auto_cleanup=False)
        engine.run_batch(as_of=d_t, product_codes=[_alert_product_for(d_t)], auto_cleanup=False)
        filters = build_query_filters("昨天的产品回撤事件", ref=date(2026, 6, 19))
        events = engine.query_events(
            since=filters["since"],
            until=filters["until"],
            drawdown_only=filters["drawdown_only"],
        )
        assert events
        assert all(evt.get("data_date") == "2026-06-18" for evt in events)


class TestSopAPI:
    def test_get_system(self):
        resp = client.get("/api/sop/system")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "rules" in data["data"]

    def test_run_batch_and_query(self):
        resp = client.post("/api/sop/events/run-batch", json={})
        assert resp.status_code == 200
        batch = resp.json()["data"]

        q = client.post("/api/sop/agent/query", json={
            "question": "5月以来产品回撤事件",
            "drawdown_only": True,
        })
        assert q.status_code == 200
        events = q.json()["data"]["events"]
        assert isinstance(events, list)

        if events:
            evt_id = events[0]["event_id"]
            run = client.post("/api/sop/agent/run", json={"event_id": evt_id})
            assert run.status_code == 200
            out = run.json()["data"]
            assert "event_description" in out
            assert "client_script" in out

            get_out = client.get(f"/api/sop/agent/output?event_id={evt_id}")
            assert get_out.status_code == 200

    def test_agent_run_not_found(self):
        resp = client.post("/api/sop/agent/run", json={"event_id": "EVT999"})
        assert resp.status_code == 404
