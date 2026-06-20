"""客户经理 ↔ 飞书账号批量对齐（无需逐个配置 open_id）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from core.advisor_feishu_cache import AdvisorFeishuCache, enrich_advisor_with_cache, validate_advisor_feishu_target
from core.config_loader import get_advisor_map, load_advisor_directory
from core.sop_feishu_client import FEISHU_BASE, FeishuApiError, FeishuClient


def _sync_cfg() -> dict[str, Any]:
    return load_advisor_directory().get("feishu_sync") or {}


class AdvisorFeishuSyncService:
    def __init__(self, client: FeishuClient | None = None) -> None:
        self.client = client or FeishuClient()
        self.cache = AdvisorFeishuCache()

    def sync_all(self, *, force: bool = False) -> dict[str, Any]:
        """
        批量对齐全部客户经理：
        1) 若配置了 department_id → 拉取部门成员按工号/手机/邮箱/姓名匹配
        2) 否则 → 对有 mobile/email 的经理批量 batch_get_id
        结果写入 data/advisor_feishu_cache.json，无需改 yaml 里的 open_id。
        """
        cfg = _sync_cfg()
        dept_id = (cfg.get("department_id") or "").strip()
        if dept_id:
            return self._sync_from_department(dept_id, force=force)
        return self._sync_by_contacts(force=force)

    def _sync_by_contacts(self, *, force: bool) -> dict[str, Any]:
        advisors = get_advisor_map()
        resolved: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, str]] = []
        pending_mobile: list[tuple[str, dict[str, Any], str]] = []
        pending_email: list[tuple[str, dict[str, Any], str]] = []

        for aid, adv in advisors.items():
            if not force:
                if (adv.get("feishu_open_id") or "").strip() or self.cache.get_open_id(aid):
                    resolved[aid] = {"status": "skipped", "reason": "已有 open_id"}
                    continue
            mobile = (adv.get("mobile") or "").strip()
            email = (adv.get("email") or "").strip()
            if mobile:
                pending_mobile.append((aid, adv, mobile))
            elif email:
                pending_email.append((aid, adv, email))
            else:
                errors.append({"advisor_id": aid, "error": "缺少 mobile / email / employee_no"})

        for chunk in _chunks(pending_mobile, 50):
            self._batch_resolve_mobile(chunk, resolved, errors)
        for chunk in _chunks(pending_email, 50):
            self._batch_resolve_email(chunk, resolved, errors)

        cache_rows = {
            aid: {
                "advisor_id": aid,
                "advisor_name": row.get("advisor_name"),
                "feishu_open_id": row["feishu_open_id"],
                "source": row.get("source", "batch_get_id"),
                "mobile": row.get("mobile", ""),
                "email": row.get("email", ""),
                "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            for aid, row in resolved.items()
            if row.get("feishu_open_id")
        }
        cached = self.cache.merge_bulk(cache_rows)

        return {
            "mode": "batch_get_id",
            "total": len(advisors),
            "resolved": sum(1 for r in resolved.values() if r.get("feishu_open_id")),
            "skipped": sum(1 for r in resolved.values() if r.get("status") == "skipped"),
            "cached": cached,
            "errors": errors,
            "details": [
                {"advisor_id": k, **v} for k, v in resolved.items() if v.get("feishu_open_id")
            ],
        }

    def _batch_resolve_mobile(
        self,
        chunk: list[tuple[str, dict[str, Any], str]],
        resolved: dict[str, dict[str, Any]],
        errors: list[dict[str, str]],
    ) -> None:
        mobiles = [x[2] for x in chunk]
        mobile_to_open = self._batch_get_id(mobiles=mobiles)
        for aid, adv, mobile in chunk:
            open_id = mobile_to_open.get(mobile)
            if open_id:
                resolved[aid] = {
                    "advisor_name": adv.get("name"),
                    "feishu_open_id": open_id,
                    "source": "batch_get_id:mobile",
                    "mobile": mobile,
                }
            else:
                errors.append({"advisor_id": aid, "error": f"飞书未找到手机号 {mobile}"})

    def _batch_resolve_email(
        self,
        chunk: list[tuple[str, dict[str, Any], str]],
        resolved: dict[str, dict[str, Any]],
        errors: list[dict[str, str]],
    ) -> None:
        emails = [x[2] for x in chunk]
        email_to_open = self._batch_get_id(emails=emails)
        for aid, adv, email in chunk:
            open_id = email_to_open.get(email)
            if open_id:
                resolved[aid] = {
                    "advisor_name": adv.get("name"),
                    "feishu_open_id": open_id,
                    "source": "batch_get_id:email",
                    "email": email,
                }
            else:
                errors.append({"advisor_id": aid, "error": f"飞书未找到邮箱 {email}"})

    def _batch_get_id(
        self,
        *,
        mobiles: list[str] | None = None,
        emails: list[str] | None = None,
    ) -> dict[str, str]:
        body: dict[str, Any] = {}
        if mobiles:
            body["mobiles"] = mobiles
        if emails:
            body["emails"] = emails
        if not body:
            return {}

        url = f"{FEISHU_BASE}/contact/v3/users/batch_get_id?user_id_type=open_id"
        with httpx.Client(timeout=self.client._timeout) as http:
            resp = http.post(url, headers=self.client._headers(), json=body)
        data = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise FeishuApiError(
                f"批量解析 open_id 失败: {data.get('msg') or resp.text}",
                code=data.get("code"),
            )

        result: dict[str, str] = {}
        for item in (data.get("data") or {}).get("user_list") or []:
            open_id = (item.get("user_id") or "").strip()
            if not open_id:
                continue
            if item.get("mobile"):
                result[str(item["mobile"])] = open_id
            if item.get("email"):
                result[str(item["email"])] = open_id
        return result

    def _sync_from_department(self, department_id: str, *, force: bool) -> dict[str, Any]:
        users = self._list_department_users(department_id)
        index = _build_feishu_user_index(users)
        advisors = get_advisor_map()
        resolved: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, str]] = []

        for aid, adv in advisors.items():
            if not force:
                if (adv.get("feishu_open_id") or "").strip() or self.cache.get_open_id(aid):
                    resolved[aid] = {"status": "skipped", "reason": "已有 open_id"}
                    continue
            match = _match_advisor_to_feishu_user(adv, index)
            if match:
                resolved[aid] = {
                    "advisor_name": adv.get("name"),
                    "feishu_open_id": match["open_id"],
                    "source": f"department:{match['matched_by']}",
                    "mobile": match.get("mobile", ""),
                    "email": match.get("email", ""),
                }
            else:
                errors.append(
                    {
                        "advisor_id": aid,
                        "error": "部门成员中未匹配到（需 employee_no / mobile / email / 姓名一致）",
                    }
                )

        cache_rows = {
            aid: {
                "advisor_id": aid,
                "advisor_name": row.get("advisor_name"),
                "feishu_open_id": row["feishu_open_id"],
                "source": row.get("source", "department"),
                "mobile": row.get("mobile", ""),
                "email": row.get("email", ""),
                "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            for aid, row in resolved.items()
            if row.get("feishu_open_id")
        }
        cached = self.cache.merge_bulk(cache_rows)

        return {
            "mode": "department",
            "department_id": department_id,
            "feishu_users_scanned": len(users),
            "total": len(advisors),
            "resolved": sum(1 for r in resolved.values() if r.get("feishu_open_id")),
            "skipped": sum(1 for r in resolved.values() if r.get("status") == "skipped"),
            "cached": cached,
            "errors": errors,
        }

    def _list_department_users(self, department_id: str) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {
                "department_id": department_id,
                "department_id_type": "open_department_id",
                "user_id_type": "open_id",
                "page_size": 50,
            }
            if page_token:
                params["page_token"] = page_token
            url = f"{FEISHU_BASE}/contact/v3/users/find_by_department"
            with httpx.Client(timeout=self.client._timeout) as http:
                resp = http.get(url, headers=self.client._headers(), params=params)
            data = resp.json()
            if resp.status_code != 200 or data.get("code") != 0:
                raise FeishuApiError(
                    f"拉取部门成员失败: {data.get('msg') or resp.text}",
                    code=data.get("code"),
                )
            block = (data.get("data") or {})
            for item in block.get("items") or []:
                users.append(item)
            page_token = block.get("page_token") or ""
            if not page_token or not block.get("has_more"):
                break
        return users


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_feishu_user_index(users: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {
        "by_employee_no": {},
        "by_mobile": {},
        "by_email": {},
        "by_name": {},
    }
    for u in users:
        open_id = (u.get("open_id") or u.get("user_id") or "").strip()
        if not open_id:
            continue
        row = {
            "open_id": open_id,
            "name": u.get("name") or "",
            "mobile": u.get("mobile") or "",
            "email": u.get("email") or "",
            "employee_no": u.get("employee_no") or u.get("employee_id") or "",
        }
        if row["employee_no"]:
            index["by_employee_no"][str(row["employee_no"]).strip()] = row
        if row["mobile"]:
            index["by_mobile"][str(row["mobile"]).strip()] = row
        if row["email"]:
            index["by_email"][str(row["email"]).strip().lower()] = row
        if row["name"]:
            index["by_name"][str(row["name"]).strip()] = row
    return index


def _match_advisor_to_feishu_user(
    advisor: dict[str, Any],
    index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    emp = (advisor.get("employee_no") or "").strip()
    if emp and emp in index["by_employee_no"]:
        row = dict(index["by_employee_no"][emp])
        row["matched_by"] = "employee_no"
        return row
    mobile = (advisor.get("mobile") or "").strip()
    if mobile and mobile in index["by_mobile"]:
        row = dict(index["by_mobile"][mobile])
        row["matched_by"] = "mobile"
        return row
    email = (advisor.get("email") or "").strip().lower()
    if email and email in index["by_email"]:
        row = dict(index["by_email"][email])
        row["matched_by"] = "email"
        return row
    name = (advisor.get("name") or "").strip()
    if name and name in index["by_name"]:
        row = dict(index["by_name"][name])
        row["matched_by"] = "name"
        return row
    return None
