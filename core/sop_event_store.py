"""SOP 事件日志持久化（JSON 文件，独立于投后陪伴）。"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
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

    @staticmethod
    def rule_log_key(hit: dict[str, Any]) -> tuple[str, str, str]:
        """产品 + 规则 + 数据日，用于跑批去重。"""
        metrics = hit.get("metrics") or {}
        data_date = metrics.get("data_date") or ""
        if not data_date and hit.get("business_no"):
            parts = str(hit["business_no"]).rsplit("_", 1)
            if len(parts) == 2:
                data_date = parts[1]
        return (
            str(hit.get("product_code") or ""),
            str(hit.get("rule_code") or ""),
            str(data_date),
        )

    @staticmethod
    def composite_event_key(evt: dict[str, Any]) -> tuple[str, str, str]:
        """产品 + 组合事件 + 数据日，用于跑批去重。"""
        return (
            str(evt.get("product_code") or ""),
            str(evt.get("composite_code") or ""),
            str(evt.get("data_date") or ""),
        )

    def existing_rule_log_keys(self, *, data_date: str | None = None) -> set[tuple[str, str, str]]:
        keys: set[tuple[str, str, str]] = set()
        for row in self._load()["rule_logs"]:
            key = self.rule_log_key(row)
            if data_date and key[2] != data_date:
                continue
            keys.add(key)
        return keys

    def existing_composite_keys(self, *, data_date: str | None = None) -> set[tuple[str, str, str]]:
        keys: set[tuple[str, str, str]] = set()
        for evt in self._load()["composite_events"]:
            key = self.composite_event_key(evt)
            if data_date and key[2] != data_date:
                continue
            keys.add(key)
        return keys

    def purge_data_date(self, data_date: str) -> dict[str, int]:
        """删除指定数据日的规则日志、组合事件及关联智能体输出。"""

        def _update(data: dict[str, Any]) -> dict[str, int]:
            removed_event_ids = {
                e["event_id"]
                for e in data["composite_events"]
                if e.get("data_date") == data_date and e.get("event_id")
            }
            rule_logs = [
                r
                for r in data["rule_logs"]
                if self.rule_log_key(r)[2] != data_date
            ]
            composite_events = [
                e for e in data["composite_events"] if e.get("data_date") != data_date
            ]
            agent_outputs = dict(data.get("agent_outputs") or {})
            for eid in removed_event_ids:
                agent_outputs.pop(eid, None)
            removed_rules = len(data["rule_logs"]) - len(rule_logs)
            removed_events = len(data["composite_events"]) - len(composite_events)
            data["rule_logs"] = rule_logs
            data["composite_events"] = composite_events
            data["agent_outputs"] = agent_outputs
            return {
                "rule_logs": removed_rules,
                "composite_events": removed_events,
                "agent_outputs": len(removed_event_ids),
            }

        return self._mutate(_update)

    def cleanup_before(self, before_date: date) -> dict[str, int]:
        """删除 data_date 严格早于 before_date 的记录（不含 before_date 当天）。"""
        cutoff = before_date.isoformat()

        def _update(data: dict[str, Any]) -> dict[str, int]:
            removed_event_ids = {
                e["event_id"]
                for e in data["composite_events"]
                if (e.get("data_date") or "") < cutoff and e.get("event_id")
            }
            rule_logs = [r for r in data["rule_logs"] if self.rule_log_key(r)[2] >= cutoff]
            composite_events = [
                e for e in data["composite_events"] if (e.get("data_date") or "") >= cutoff
            ]
            agent_outputs = dict(data.get("agent_outputs") or {})
            for eid in removed_event_ids:
                agent_outputs.pop(eid, None)
            removed_rules = len(data["rule_logs"]) - len(rule_logs)
            removed_events = len(data["composite_events"]) - len(composite_events)
            data["rule_logs"] = rule_logs
            data["composite_events"] = composite_events
            data["agent_outputs"] = agent_outputs
            return {
                "rule_logs": removed_rules,
                "composite_events": removed_events,
                "agent_outputs": len(removed_event_ids),
            }

        return self._mutate(_update)

    def dedupe_all(self) -> dict[str, int]:
        """合并历史重复记录：同 data_date+产品+规则/组合事件只保留一条。"""

        def _pick_best_event(rows: list[dict[str, Any]]) -> dict[str, Any]:
            def score(e: dict[str, Any]) -> tuple[int, str]:
                status = e.get("agent_status") or "pending"
                has_out = 1 if status == "done" else 0
                return (has_out, e.get("event_id") or "")

            return max(rows, key=score)

        def _update(data: dict[str, Any]) -> dict[str, int]:
            agent_outputs = dict(data.get("agent_outputs") or {})
            by_event: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for evt in data["composite_events"]:
                by_event.setdefault(self.composite_event_key(evt), []).append(evt)

            kept_events: list[dict[str, Any]] = []
            removed_event_ids: set[str] = set()
            for group in by_event.values():
                best = _pick_best_event(group)
                kept_events.append(best)
                for other in group:
                    if other.get("event_id") != best.get("event_id") and other.get("event_id"):
                        removed_event_ids.add(other["event_id"])

            by_rule: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in data["rule_logs"]:
                key = self.rule_log_key(row)
                prev = by_rule.get(key)
                if not prev or (row.get("id") or 0) > (prev.get("id") or 0):
                    by_rule[key] = row

            for eid in removed_event_ids:
                agent_outputs.pop(eid, None)

            removed_events = len(data["composite_events"]) - len(kept_events)
            removed_rules = len(data["rule_logs"]) - len(by_rule.values())
            data["composite_events"] = kept_events
            data["rule_logs"] = list(by_rule.values())
            data["agent_outputs"] = agent_outputs
            return {
                "rule_logs": removed_rules,
                "composite_events": removed_events,
                "agent_outputs": len(removed_event_ids),
            }

        return self._mutate(_update)

    def purge_all(self) -> dict[str, int]:
        """清空全部规则日志、组合事件及智能体输出。"""

        def _update(data: dict[str, Any]) -> dict[str, int]:
            removed = {
                "rule_logs": len(data["rule_logs"]),
                "composite_events": len(data["composite_events"]),
                "agent_outputs": len(data.get("agent_outputs") or {}),
            }
            data["rule_logs"] = []
            data["composite_events"] = []
            data["agent_outputs"] = {}
            return removed

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
                        evt["status_label"] = "已生成"
                    elif output.get("agent_status") == "failed":
                        evt["status_label"] = "生成失败"
                    break

        self._mutate(_update)

    def get_agent_output(self, event_id: str) -> dict[str, Any] | None:
        return self._load()["agent_outputs"].get(event_id)

    def list_pushable_event_ids(self, *, limit: int = 20) -> list[str]:
        """agent 已完成且尚未成功推送的事件。"""
        data = self._load()
        outputs = data.get("agent_outputs") or {}
        rows = []
        for evt in data["composite_events"]:
            eid = evt.get("event_id")
            if not eid:
                continue
            out = outputs.get(eid)
            if not out or out.get("agent_status") != "done":
                continue
            if evt.get("push_status") == "sent":
                continue
            rows.append(evt)
        rows.sort(key=lambda e: e.get("trigger_time", ""), reverse=True)
        ids = [e["event_id"] for e in rows if e.get("event_id")]
        if limit > 0:
            return ids[:limit]
        return ids

    def save_push_result(
        self,
        event_id: str,
        status: str,
        deliveries: list[dict[str, Any]],
        *,
        note: str | None = None,
    ) -> None:
        def _update(data: dict[str, Any]) -> None:
            for evt in data["composite_events"]:
                if evt.get("event_id") != event_id:
                    continue
                evt["push_status"] = status
                evt["push_deliveries"] = deliveries
                evt["push_note"] = note
                evt["push_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if deliveries:
                    evt["push_sent_count"] = sum(
                        1 for d in deliveries if d.get("status") == "sent"
                    )
                    evt["push_failed_count"] = sum(
                        1 for d in deliveries if d.get("status") == "failed"
                    )
                if status == "sent":
                    evt["status_label"] = "已推送"
                elif status == "partial":
                    evt["status_label"] = "部分推送"
                elif status == "failed":
                    evt["status_label"] = "推送失败"
                break
            out = data["agent_outputs"].get(event_id)
            if out is not None:
                out["push_status"] = status
                out["push_deliveries"] = deliveries

        self._mutate(_update)

    def stats(self) -> dict[str, Any]:
        data = self._load()
        events = data["composite_events"]
        pending = sum(
            1
            for e in events
            if e.get("agent_status") in (None, "pending", "failed", "running")
        )
        dates = sorted(
            {
                (e.get("data_date") or (e.get("trigger_time") or "")[:10])
                for e in events
                if e.get("data_date") or e.get("trigger_time")
            }
        )
        dates = [d for d in dates if d]
        return {
            "composite_events": len(events),
            "rule_logs": len(data["rule_logs"]),
            "agent_outputs": len(data.get("agent_outputs") or {}),
            "pending": pending,
            "data_date_min": dates[0] if dates else None,
            "data_date_max": dates[-1] if dates else None,
            "latest_data_date": dates[-1] if dates else None,
        }
