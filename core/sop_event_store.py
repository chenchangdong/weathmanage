"""SOP 事件日志持久化（JSON 文件，独立于投后陪伴）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EVENT_FILE = DATA_DIR / "sop_events.json"
_FILE_LOCK = threading.Lock()


def _default_payload() -> dict[str, Any]:
    return {
        "next_event_seq": 1,
        "rule_logs": [],
        "composite_events": [],
        "agent_outputs": {},
    }


class SopEventStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or EVENT_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_payload()
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = self.path.with_suffix(".json.corrupt")
            if self.path.exists():
                self.path.replace(backup)
            return _default_payload()
        if not isinstance(data, dict):
            return _default_payload()
        data.setdefault("rule_logs", [])
        data.setdefault("composite_events", [])
        data.setdefault("agent_outputs", {})
        data.setdefault("next_event_seq", 1)
        return data

    def _save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
        tmp.replace(self.path)

    def _mutate(self, fn) -> Any:
        with _FILE_LOCK:
            data = self._load()
            result = fn(data)
            self._save(data)
            return result

    def next_event_id(self) -> str:
        def _update(data: dict[str, Any]) -> str:
            seq = int(data.get("next_event_seq") or 1)
            data["next_event_seq"] = seq + 1
            return f"EVT{seq:02d}"

        return self._mutate(_update)

    def append_rule_logs(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not hits:
            return []

        def _update(data: dict[str, Any]) -> list[dict[str, Any]]:
            start_id = len(data["rule_logs"]) + 1
            saved: list[dict[str, Any]] = []
            for i, hit in enumerate(hits):
                row = {**hit, "id": start_id + i}
                data["rule_logs"].append(row)
                saved.append(row)
            return saved

        return self._mutate(_update)

    def append_composite_events(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not events:
            return []

        def _update(data: dict[str, Any]) -> list[dict[str, Any]]:
            saved: list[dict[str, Any]] = []
            for evt in events:
                data["composite_events"].append(evt)
                saved.append(evt)
            return saved

        return self._mutate(_update)

    def list_rule_logs(
        self,
        *,
        business_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        data = self._load()
        rows = list(data["rule_logs"])
        if business_type:
            rows = [r for r in rows if r.get("business_type") == business_type]
        rows.sort(key=lambda r: r.get("trigger_time", ""), reverse=True)
        return rows[:limit]

    def list_composite_events(self) -> list[dict[str, Any]]:
        return list(self._load()["composite_events"])

    def get_composite_event(self, event_id: str) -> dict[str, Any] | None:
        for evt in self.list_composite_events():
            if evt.get("event_id") == event_id:
                return evt
        return None

    def set_agent_status(self, event_id: str, status: str) -> None:
        def _update(data: dict[str, Any]) -> None:
            for evt in data["composite_events"]:
                if evt.get("event_id") == event_id:
                    evt["agent_status"] = status
                    break

        self._mutate(_update)

    def reset_stale_running(self, *, to_status: str = "pending") -> int:
        """将中断遗留的 running 状态重置，避免批量任务永远跳过。"""

        def _update(data: dict[str, Any]) -> int:
            count = 0
            for evt in data["composite_events"]:
                if evt.get("agent_status") == "running":
                    evt["agent_status"] = to_status
                    count += 1
            return count

        return self._mutate(_update)

    def list_pending_event_ids(self, *, limit: int | None = None) -> list[str]:
        rows = [
            e
            for e in self.list_composite_events()
            if e.get("agent_status") in (None, "pending", "failed", "running")
        ]
        rows.sort(key=lambda e: e.get("trigger_time", ""), reverse=True)
        ids = [e["event_id"] for e in rows if e.get("event_id")]
        if limit is not None and limit > 0:
            return ids[:limit]
        return ids

    def save_agent_output(self, event_id: str, output: dict[str, Any]) -> None:
        def _update(data: dict[str, Any]) -> None:
            data["agent_outputs"][event_id] = output
            for evt in data["composite_events"]:
                if evt.get("event_id") == event_id:
                    evt["agent_status"] = output.get("agent_status", "done")
                    if output.get("agent_status") == "done":
                        evt["status"] = 1
                        evt["status_label"] = "1 已确认"
                    break

        self._mutate(_update)

    def get_agent_output(self, event_id: str) -> dict[str, Any] | None:
        return self._load()["agent_outputs"].get(event_id)
