"""SOP 事件查询 — 从自然语言问题解析日期范围（本地规则，不调用 LLM）。"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any


def parse_date_range(question: str, *, ref: date | None = None) -> tuple[str | None, str | None]:
    """从问题中解析 inclusive 日期范围 (since, until)，ISO 格式。"""
    today = ref or date.today()
    q = (question or "").strip()

    if "昨天" in q or "昨日" in q:
        d = today - timedelta(days=1)
        iso = d.isoformat()
        return iso, iso
    if "前天" in q:
        d = today - timedelta(days=2)
        iso = d.isoformat()
        return iso, iso
    if "今天" in q or "今日" in q:
        iso = today.isoformat()
        return iso, iso

    m = re.search(r"最近\s*(\d+)\s*天", q)
    if m:
        n = max(1, int(m.group(1)))
        since = (today - timedelta(days=n - 1)).isoformat()
        return since, today.isoformat()

    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", q)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        iso = d.isoformat()
        return iso, iso

    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?", q)
    if m and "5月" not in q and "五月" not in q:
        d = date(today.year, int(m.group(1)), int(m.group(2)))
        iso = d.isoformat()
        return iso, iso

    if "5月" in q or "五月" in q:
        return f"{today.year}-05-01", today.isoformat()

    return None, None


def format_range_label(since: str | None, until: str | None) -> str:
    if since and until:
        if since == until:
            return since
        return f"{since} 至 {until}"
    if since:
        return f"{since} 起"
    if until:
        return f"至 {until}"
    return "全部时段"


def build_query_filters(
    question: str,
    *,
    since: str | None = None,
    until: str | None = None,
    drawdown_only: bool = True,
    ref: date | None = None,
) -> dict[str, Any]:
    """合并显式参数与问题解析结果。"""
    parsed_since, parsed_until = parse_date_range(question, ref=ref)
    final_since = since or parsed_since
    final_until = until or parsed_until
    dd = drawdown_only or ("回撤" in (question or ""))
    return {
        "since": final_since,
        "until": final_until,
        "drawdown_only": dd,
        "range_label": format_range_label(final_since, final_until),
    }
