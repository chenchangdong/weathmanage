"""SOP 6.1 / 6.2 unit tests."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.sop_event_store import SopEventStore
from core.sop_rule_engine import SopRuleEngine, evaluate_expression, mock_product_metrics
from main import app

client = TestClient(app)


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

    def test_run_batch_creates_logs(self, tmp_path, monkeypatch):
        store = SopEventStore(path=tmp_path / "sop_events.json")
        engine = SopRuleEngine(store=store)
        result = engine.run_batch(as_of=date(2026, 6, 2), product_codes=["PROD001"])
        assert result["products_scanned"] == 1
        logs = store.list_rule_logs()
        assert isinstance(logs, list)


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
