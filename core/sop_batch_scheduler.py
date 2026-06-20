"""SOP 6.2.1 — 定时跑批调度（默认每日 20:00）。"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

from core.config_loader import load_sop_agent_system

_lock = threading.Lock()
_last_batch_date: str | None = None
_last_batch_result: dict[str, Any] | None = None
_last_scheduled_slot: str | None = None
_scheduler_thread: threading.Thread | None = None


def _schedule_cfg() -> dict[str, Any]:
    return load_sop_agent_system().get("batch_schedule") or {}


def _cron_label(hour: int, minute: int) -> str:
    return f"每天 {hour:02d}:{minute:02d}"


def get_scheduler_status() -> dict[str, Any]:
    cfg = _schedule_cfg()
    hour = int(cfg.get("hour", 20))
    minute = int(cfg.get("minute", 0))
    enabled = bool(cfg.get("enabled", False))
    return {
        "enabled": enabled,
        "hour": hour,
        "minute": minute,
        "cron": f"0 {minute} {hour} * * ?",
        "cron_label": _cron_label(hour, minute),
        "run_agent_after_batch": bool(cfg.get("run_agent_after_batch", True)),
        "push_feishu_after_agent": bool(cfg.get("push_feishu_after_agent", False))
        if cfg.get("run_agent_after_batch", True)
        else False,
        "trigger_name": cfg.get("trigger_name", "投后SOP事件跑批"),
        "trigger_type": cfg.get("trigger_type", "CRON"),
        "description": cfg.get(
            "description",
            "每日按 SOP 产品库与规则扫描，识别组合事件并写入事件库",
        ),
        "timezone_note": cfg.get("timezone_note", "服务器本地时区"),
        "scheduler_running": bool(_scheduler_thread and _scheduler_thread.is_alive()),
        "last_batch_date": _last_batch_date,
        "last_batch_result": _last_batch_result,
        "last_trigger_time": (_last_batch_result or {}).get("trigger_time"),
        "next_run_hint": _next_run_hint(enabled, hour, minute),
    }


def _next_run_hint(enabled: bool, hour: int, minute: int) -> str | None:
    if not enabled:
        return None
    now = datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.strftime("%Y-%m-%d %H:%M")


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
        push_result: dict[str, Any] = {"processed": 0}
        cfg = _schedule_cfg()
        push_cfg = load_sop_agent_system().get("feishu_push") or {}
        run_agent = bool(cfg.get("run_agent_after_batch", True))
        push_after_agent = run_agent and bool(cfg.get("push_feishu_after_agent", False))

        if run_agent:
            pending_ids = [
                e["event_id"]
                for e in batch_result.get("events") or []
                if e.get("agent_status") == "pending"
            ]
            if pending_ids:
                agent_result = SopAgentService().run_batch_for_events(pending_ids)

        if push_after_agent and push_cfg.get("enabled", True):
            from core.sop_push_service import SopPushService

            done_ids = [
                o.get("event_id")
                for o in (agent_result.get("outputs") or [])
                if o.get("event_id")
            ]
            if done_ids:
                push_result = SopPushService().push_batch(done_ids, all_done_unpushed=False)

        result = {
            "as_of": today,
            "trigger_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "batch": batch_result,
            "agent": agent_result,
            "feishu_push": push_result,
        }
        _last_batch_date = today
        _last_batch_result = result
        return result


def _scheduler_loop() -> None:
    global _last_scheduled_slot
    while True:
        try:
            cfg = _schedule_cfg()
            if cfg.get("enabled", False):
                now = datetime.now()
                hour = int(cfg.get("hour", 20))
                minute = int(cfg.get("minute", 0))
                if now.hour == hour and now.minute == minute:
                    slot = f"{now.date().isoformat()}T{hour:02d}:{minute:02d}"
                    if _last_scheduled_slot != slot:
                        run_scheduled_batch(force=False)
                        _last_scheduled_slot = slot
        except Exception:
            pass
        time.sleep(30)


def ensure_scheduler_running() -> None:
    start_scheduler()


def start_scheduler() -> None:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, name="sop-batch-scheduler", daemon=True
    )
    _scheduler_thread.start()
