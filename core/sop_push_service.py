"""SOP 6.2.5 — 飞书一对一推送编排。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.config_loader import get_advisor_map, load_advisor_directory, load_sop_agent_system
from core.advisor_feishu_sync import AdvisorFeishuSyncService
from core.sop_audience_resolver import (
    get_advisor_record,
    resolve_event_audiences,
    validate_advisor_feishu_target,
)
from core.sop_event_store import SopEventStore
from core.sop_feishu_card_builder import build_push_card
from core.sop_feishu_client import FeishuApiError, FeishuClient


class SopPushService:
    def __init__(self, store: SopEventStore | None = None) -> None:
        self.store = store or SopEventStore()
        self.client = FeishuClient()

    def preview_event(self, event_id: str) -> dict[str, Any]:
        event = self._require_event(event_id)
        output = self.store.get_agent_output(event_id)
        audiences = resolve_event_audiences(event.get("product_code") or "")
        targets = []
        for aud in audiences:
            advisor = get_advisor_record(aud["advisor_id"]) or {}
            targets.append(
                {
                    **aud,
                    "feishu_ready": validate_advisor_feishu_target(advisor) is None,
                    "feishu_hint": validate_advisor_feishu_target(advisor),
                    "has_agent_output": bool(output),
                }
            )
        return {
            "event_id": event_id,
            "product_code": event.get("product_code"),
            "audience_count": len(targets),
            "message_count": len(targets),
            "targets": targets,
            "agent_status": event.get("agent_status"),
        }

    def push_event(self, event_id: str, *, force: bool = False) -> dict[str, Any]:
        push_cfg = load_sop_agent_system().get("feishu_push") or {}
        if not push_cfg.get("enabled", True):
            raise ValueError("飞书推送已在配置中关闭（feishu_push.enabled=false）")

        self._maybe_sync_advisors_before_push()

        event = self._require_event(event_id)
        output = self.store.get_agent_output(event_id)
        if not output or output.get("agent_status") != "done":
            raise ValueError(f"事件 {event_id} 尚未完成 6.2 内容生成，请先运行智能体")

        if not force and event.get("push_status") == "sent":
            return {
                "event_id": event_id,
                "skipped": True,
                "reason": "已推送过，如需重发请 force=true",
                "deliveries": event.get("push_deliveries") or [],
            }

        audiences = resolve_event_audiences(event.get("product_code") or "")
        if not audiences:
            result = {
                "event_id": event_id,
                "sent": 0,
                "failed": 0,
                "skipped_no_holders": True,
                "deliveries": [],
            }
            self.store.save_push_result(event_id, "skipped", result["deliveries"], note="无持有客户")
            return result

        retry = max(0, int(push_cfg.get("retry") or 2))
        deliveries: list[dict[str, Any]] = []
        sent = 0
        failed = 0

        for aud in audiences:
            advisor = get_advisor_record(aud["advisor_id"]) or {}
            missing = validate_advisor_feishu_target(advisor)
            if missing:
                failed += 1
                deliveries.append(
                    {
                        "customer_id": aud["customer_id"],
                        "customer_name": aud["customer_name"],
                        "advisor_id": aud["advisor_id"],
                        "advisor_name": aud["advisor_name"],
                        "status": "failed",
                        "error": missing,
                    }
                )
                continue

            card = build_push_card(event=event, output=output, audience=aud)
            last_error: str | None = None
            message_id = ""
            for attempt in range(retry + 1):
                try:
                    open_id = self.client.resolve_open_id({**advisor, "id": aud["advisor_id"]})
                    message_id = self.client.send_interactive_card(open_id, card)
                    last_error = None
                    break
                except FeishuApiError as exc:
                    last_error = str(exc)
                    if attempt >= retry:
                        break

            if last_error:
                failed += 1
                deliveries.append(
                    {
                        "customer_id": aud["customer_id"],
                        "customer_name": aud["customer_name"],
                        "advisor_id": aud["advisor_id"],
                        "advisor_name": aud["advisor_name"],
                        "status": "failed",
                        "error": last_error,
                    }
                )
            else:
                sent += 1
                deliveries.append(
                    {
                        "customer_id": aud["customer_id"],
                        "customer_name": aud["customer_name"],
                        "advisor_id": aud["advisor_id"],
                        "advisor_name": aud["advisor_name"],
                        "status": "sent",
                        "message_id": message_id,
                        "pushed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        status = "sent" if sent and not failed else ("partial" if sent else "failed")
        self.store.save_push_result(event_id, status, deliveries)
        return {
            "event_id": event_id,
            "sent": sent,
            "failed": failed,
            "status": status,
            "deliveries": deliveries,
        }

    def push_batch(
        self,
        event_ids: list[str] | None = None,
        *,
        all_done_unpushed: bool = False,
        limit: int = 20,
        force: bool = False,
    ) -> dict[str, Any]:
        if event_ids:
            targets = list(event_ids)
        elif all_done_unpushed:
            targets = self.store.list_pushable_event_ids(limit=limit)
        else:
            targets = self.store.list_pushable_event_ids(limit=limit)

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for eid in targets[:limit]:
            try:
                results.append(self.push_event(eid, force=force))
            except Exception as exc:
                errors.append({"event_id": eid, "error": str(exc)})

        return {
            "processed": len(results),
            "failed_events": len(errors),
            "results": results,
            "errors": errors,
        }

    def resolve_advisor_open_id(self, advisor_id: str) -> dict[str, Any]:
        advisor = get_advisor_record(advisor_id)
        if not advisor:
            raise ValueError(f"客户经理不存在: {advisor_id}")
        open_id = self.client.resolve_open_id({**advisor, "id": advisor_id})
        return {
            "advisor_id": advisor_id,
            "advisor_name": advisor.get("name"),
            "feishu_open_id": open_id,
            "hint": "可将 feishu_open_id 写入 config/advisor_directory.yaml 避免重复解析",
        }

    def probe(self) -> dict[str, Any]:
        return self.client.probe_credentials()

    def sync_advisors(self, *, force: bool = False) -> dict[str, Any]:
        return AdvisorFeishuSyncService(self.client).sync_all(force=force)

    def _maybe_sync_advisors_before_push(self) -> None:
        sync_cfg = load_advisor_directory().get("feishu_sync") or {}
        if not sync_cfg.get("sync_before_push", True):
            return
        AdvisorFeishuSyncService(self.client).sync_all(force=False)

    def _require_event(self, event_id: str) -> dict[str, Any]:
        event = self.store.get_composite_event(event_id)
        if not event:
            raise ValueError(f"事件不存在: {event_id}")
        return event
