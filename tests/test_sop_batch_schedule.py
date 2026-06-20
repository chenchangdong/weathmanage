"""SOP 定时跑批配置与调度状态。"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestSopBatchSchedule:
    def test_schedule_status_has_push_flag(self):
        resp = client.get("/api/sop/agent/schedule/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "push_feishu_after_agent" in data
        assert "trigger_name" in data

    def test_schedule_triggers_list(self):
        resp = client.get("/api/sop/agent/schedule/triggers")
        assert resp.status_code == 200
        triggers = resp.json()["data"]["triggers"]
        assert len(triggers) == 1
        assert triggers[0]["id"] == "sop_event_batch"
        assert "push_feishu_after_agent" in triggers[0]

    def test_save_schedule_config(self):
        resp = client.put(
            "/api/sop/agent/schedule/config",
            json={
                "enabled": True,
                "hour": 20,
                "minute": 30,
                "run_agent_after_batch": False,
                "push_feishu_after_agent": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["hour"] == 20
        assert data["minute"] == 30
        assert data["run_agent_after_batch"] is False
        assert data["push_feishu_after_agent"] is False

    def test_save_push_requires_agent(self):
        resp = client.put(
            "/api/sop/agent/schedule/config",
            json={
                "enabled": True,
                "hour": 20,
                "minute": 0,
                "run_agent_after_batch": True,
                "push_feishu_after_agent": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_agent_after_batch"] is True
        assert data["push_feishu_after_agent"] is True
        assert "飞书推送" in client.get("/api/sop/agent/schedule/triggers").json()["data"]["triggers"][0]["action_label"]

        # restore
        client.put(
            "/api/sop/agent/schedule/config",
            json={
                "enabled": True,
                "hour": 20,
                "minute": 0,
                "run_agent_after_batch": True,
                "push_feishu_after_agent": False,
            },
        )
