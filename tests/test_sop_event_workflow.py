"""Tests for SOP event workflow display."""

from core.sop_event_workflow import FLOW_TOOLTIP, workflow_display


def test_workflow_pending():
    d = workflow_display({"agent_status": None, "push_status": None})
    assert d["agent_label"] == "待生成"
    assert d["push_label"] == "—"


def test_workflow_done_waiting_push():
    d = workflow_display({"agent_status": "done", "push_status": None})
    assert d["agent_label"] == "已生成"
    assert d["push_label"] == "待推送"


def test_workflow_done_sent():
    d = workflow_display({"agent_status": "done", "push_status": "sent"})
    assert d["push_label"] == "已推送"


def test_workflow_failed_no_push():
    d = workflow_display({"agent_status": "failed", "push_status": "sent"})
    assert d["agent_label"] == "生成失败"
    assert d["push_label"] == "—"


def test_tooltip_mentions_legacy():
    assert "已确认" in FLOW_TOOLTIP
