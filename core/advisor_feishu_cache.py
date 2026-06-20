"""客户经理飞书 open_id 持久化缓存（首次解析后自动写入，无需手工配置 open_id）。"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CACHE_FILE = DATA_DIR / "advisor_feishu_cache.json"
_FILE_LOCK = threading.Lock()


def _default_payload() -> dict[str, Any]:
    return {"version": 1, "updated_at": None, "advisors": {}}


class AdvisorFeishuCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CACHE_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_payload()
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _default_payload()
        if not isinstance(data, dict):
            return _default_payload()
        data.setdefault("advisors", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
        tmp.replace(self.path)

    def get(self, advisor_id: str) -> dict[str, Any] | None:
        row = self._load()["advisors"].get(advisor_id)
        return dict(row) if isinstance(row, dict) else None

    def get_open_id(self, advisor_id: str) -> str | None:
        row = self.get(advisor_id)
        if not row:
            return None
        oid = (row.get("feishu_open_id") or "").strip()
        return oid or None

    def set(
        self,
        advisor_id: str,
        *,
        feishu_open_id: str,
        source: str,
        advisor_name: str | None = None,
        mobile: str | None = None,
        email: str | None = None,
    ) -> None:
        with _FILE_LOCK:
            data = self._load()
            data["advisors"][advisor_id] = {
                "advisor_id": advisor_id,
                "advisor_name": advisor_name,
                "feishu_open_id": feishu_open_id,
                "source": source,
                "mobile": mobile or "",
                "email": email or "",
                "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save(data)

    def merge_bulk(self, rows: dict[str, dict[str, Any]]) -> int:
        if not rows:
            return 0
        with _FILE_LOCK:
            data = self._load()
            count = 0
            for aid, row in rows.items():
                if not row.get("feishu_open_id"):
                    continue
                data["advisors"][aid] = row
                count += 1
            if count:
                self._save(data)
            return count

    def list_all(self) -> dict[str, dict[str, Any]]:
        return dict(self._load().get("advisors") or {})


def enrich_advisor_with_cache(advisor: dict[str, Any]) -> dict[str, Any]:
    """合并持久化缓存中的 open_id（运行时视图）。"""
    merged = dict(advisor)
    aid = str(advisor.get("id") or "")
    if aid and not (merged.get("feishu_open_id") or "").strip():
        cached = AdvisorFeishuCache().get_open_id(aid)
        if cached:
            merged["feishu_open_id"] = cached
            merged["_feishu_open_id_source"] = "cache"
    return merged


def validate_advisor_feishu_target(advisor: dict[str, Any]) -> str | None:
    enriched = enrich_advisor_with_cache(advisor)
    if (enriched.get("feishu_open_id") or "").strip():
        return None
    if (advisor.get("mobile") or "").strip():
        return None
    if (advisor.get("email") or "").strip():
        return None
    if (advisor.get("employee_no") or "").strip():
        return None
    return (
        "请配置 mobile / email / employee_no 之一，或执行 POST /api/sop/agent/feishu/sync-advisors "
        "从飞书通讯录批量对齐"
    )
