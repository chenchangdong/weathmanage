"""SOP 6.2.1 — 定时跑批调度（默认每日 21:00）。"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any

from core.config_loader import load_sop_agent_system

_lock = threading.Lock()
_last_batch_date: str | None = None
_last_batch_result: dict[str, Any] | None = None
_scheduler_thread: threading.Thread | None = None


def get_scheduler_status() -> dict[str, Any]:
    cfg = load_sop_agent_system().get("batch_schedule") or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "hour": cfg.get("hour", 21),
        "minute": cfg.get("minute", 0),
        "run_agent_after_batch": bool(cfg.get("run_agent_after_batch", True)),
        "last_batch_date": _last_batch_date,
        "last_batch_result": _last_batch_result,
    }


def run_scheduled_batch(*, force: bool = False) -> dict[str, Any]:
    """执行 6.1 跑批，可选自动运行 6.2 管道。"""
    global _last_batch_date, _last_batch_result

    today = date.today().isoformat()
    with _lock:
        if not force and _last_batch_date == today:
            return _last_batch_result or {"skipped": True, "reason": "今日已跑批"}

        from core.sop_rule_engine import SopRuleEngine
        from core.sop_agent_service import SopAgentService

        engine = SopRuleEngine()
        engine.reload()
        batch_result = engine.run_batch(as_of=date.today())

        agent_result: dict[str, Any] = {"processed": 0, "outputs": []}
        cfg = load_sop_agent_system().get("batch_schedule") or {}
        if cfg.get("run_agent_after_batch", True):
            pending_ids = [
                e["event_id"]
                for e in batch_result.get("events") or []
                if e.get("agent_status") == "pending"
            ]
            if pending_ids:
                agent_result = SopAgentService().run_batch_for_events(pending_ids)

        result = {
            "as_of": today,
            "trigger_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "batch": batch_result,
            "agent": agent_result,
        }
        _last_batch_date = today
        _last_batch_result = result
        return result


def _scheduler_loop() -> None:
    while True:
        try:
            cfg = load_sop_agent_system().get("batch_schedule") or {}
            if cfg.get("enabled", False):
                now = datetime.now()
                if now.hour == int(cfg.get("hour", 21)) and now.minute == int(
                    cfg.get("minute", 0)
                ):
                    run_scheduled_batch()
        except Exception:
            pass
        time.sleep(30)


def start_scheduler() -> None:
    global _scheduler_thread
    cfg = load_sop_agent_system().get("batch_schedule") or {}
    if not cfg.get("enabled", False):
        return
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, name="sop-batch-scheduler", daemon=True
    )
    _scheduler_thread.start()
