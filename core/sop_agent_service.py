"""SOP 6.2 — 投后跟踪智能体（事件描述、产品信息、投研分析、对客话术；不含推送）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.sop_agent_pipeline import SopAgentPipeline
from core.sop_event_store import SopEventStore
from core.sop_rule_engine import SopRuleEngine


class SopAgentService:
    """独立于投后陪伴的 SOP 投后智能体。"""

    def __init__(self) -> None:
        self.store = SopEventStore()
        self.engine = SopRuleEngine(self.store)
        self.pipeline = SopAgentPipeline()

    def run_for_event(self, event_id: str, *, use_llm: bool = True) -> dict[str, Any]:
        event = self.store.get_composite_event(event_id)
        if not event:
            raise ValueError(f"事件不存在: {event_id}")

        self.store.set_agent_status(event_id, "running")
        try:
            output = self.pipeline.run(event, use_llm=use_llm)
            self.store.save_agent_output(event_id, output)
            return output
        except Exception:
            self.store.set_agent_status(event_id, "failed")
            raise

    def run_batch_for_events(
        self,
        event_ids: list[str] | None = None,
        *,
        limit: int = 20,
        use_llm: bool = False,
    ) -> dict[str, Any]:
        """对 pending 或指定事件批量运行 6.2 管道（默认每批最多 20 条）。"""
        reset = self.store.reset_stale_running()
        if event_ids:
            targets = list(event_ids)
        else:
            targets = self.store.list_pending_event_ids(limit=0)

        total_pending = len(targets)
        if limit > 0:
            targets = targets[:limit]

        outputs: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for eid in targets:
            try:
                outputs.append(self.run_for_event(eid, use_llm=use_llm))
            except Exception as exc:
                errors.append({"event_id": eid, "error": str(exc)})

        remaining = max(0, total_pending - len(targets))
        return {
            "processed": len(outputs),
            "failed": len(errors),
            "batch_size": len(targets),
            "total_pending": total_pending,
            "remaining_pending": remaining,
            "reset_running": reset,
            "limit": limit,
            "use_llm": use_llm,
            "outputs": [{"event_id": o.get("event_id"), "source": o.get("source")} for o in outputs],
            "errors": errors,
        }

    def query_and_summarize(
        self,
        question: str,
        *,
        since: str | None = None,
        drawdown_only: bool = True,
    ) -> dict[str, Any]:
        """6.2.1 风格：根据自然语言问题查询事件并生成摘要。"""
        since_date = since
        if "5月" in question or "五月" in question:
            since_date = since_date or f"{date.today().year}-05-01"
        events = self.engine.query_events(
            since=since_date,
            drawdown_only=drawdown_only or "回撤" in question,
        )
        total = len(self.store.list_composite_events())
        pending = sum(
            1 for e in self.store.list_composite_events()
            if e.get("agent_status") in (None, "pending")
        )
        summary = (
            f"根据查询结果，{since_date or '全部时段'}以来共检索到 {len(events)} 条"
            f"与产品回撤直接相关的事件（库内组合事件 {total} 条，待运行智能体 {pending} 条）。"
        )
        return {
            "question": question,
            "since": since_date,
            "summary": summary,
            "events": events,
            "total_in_store": total,
            "pending_agent": pending,
        }
