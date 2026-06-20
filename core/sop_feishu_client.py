"""飞书开放平台 — tenant token、用户 ID 解析、私聊消息发送。"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from core.advisor_feishu_cache import AdvisorFeishuCache, enrich_advisor_with_cache
from core.config_loader import get_feishu_app_credentials

FEISHU_BASE = "https://open.feishu.cn/open-apis"


class FeishuApiError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, log_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.log_id = log_id


class FeishuClient:
    def __init__(self, *, timeout: float = 15.0) -> None:
        self._timeout = timeout
        self._token: str | None = None
        self._token_expire_at: float = 0.0
        self._open_id_cache: dict[str, str] = {}

    def _app_credentials(self) -> tuple[str, str]:
        app_id, app_secret = get_feishu_app_credentials()
        if not app_id or not app_secret:
            raise FeishuApiError(
                "未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，请在项目根目录 .env 中设置"
            )
        return app_id, app_secret

    def tenant_access_token(self, *, force_refresh: bool = False) -> str:
        now = time.time()
        if not force_refresh and self._token and now < self._token_expire_at - 60:
            return self._token

        app_id, app_secret = self._app_credentials()
        url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json={"app_id": app_id, "app_secret": app_secret})
        data = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise FeishuApiError(
                f"获取 tenant_access_token 失败: {data.get('msg') or resp.text}",
                code=data.get("code"),
            )
        self._token = str(data["tenant_access_token"])
        self._token_expire_at = now + int(data.get("expire", 7200))
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def resolve_open_id(self, advisor: dict[str, Any]) -> str:
        """优先缓存/yaml 中的 open_id；否则用手机号/邮箱向飞书换取并持久化缓存。"""
        advisor_id = str(advisor.get("id") or "")
        enriched = enrich_advisor_with_cache({**advisor, "id": advisor_id}) if advisor_id else advisor

        direct = (enriched.get("feishu_open_id") or advisor.get("feishu_open_id") or "").strip()
        if direct:
            return direct

        cached = self._open_id_cache.get(advisor_id)
        if cached:
            return cached

        persistent = AdvisorFeishuCache().get_open_id(advisor_id) if advisor_id else None
        if persistent:
            self._open_id_cache[advisor_id] = persistent
            return persistent

        mobile = (advisor.get("mobile") or "").strip()
        email = (advisor.get("email") or "").strip()
        if not mobile and not email:
            raise FeishuApiError(
                f"客户经理 {advisor.get('name') or advisor_id} 未配置 feishu_open_id / mobile / email。"
                f"可执行 POST /api/sop/agent/feishu/sync-advisors 批量对齐"
            )

        body: dict[str, Any] = {}
        if mobile:
            body["mobiles"] = [mobile]
        if email:
            body["emails"] = [email]

        url = f"{FEISHU_BASE}/contact/v3/users/batch_get_id?user_id_type=open_id"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=self._headers(), json=body)
        data = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise FeishuApiError(
                f"解析飞书 open_id 失败: {data.get('msg') or resp.text}。"
                f"请确认应用已开通 contact:user.base:readonly 且手机号/邮箱与飞书账号一致",
                code=data.get("code"),
            )

        user_list = (data.get("data") or {}).get("user_list") or []
        for item in user_list:
            open_id = (item.get("user_id") or "").strip()
            if open_id:
                if advisor_id:
                    self._open_id_cache[advisor_id] = open_id
                    AdvisorFeishuCache().set(
                        advisor_id,
                        feishu_open_id=open_id,
                        source="lazy_resolve",
                        advisor_name=advisor.get("name"),
                        mobile=mobile,
                        email=email,
                    )
                return open_id

        raise FeishuApiError(
            f"未在飞书通讯录找到 {advisor.get('name') or advisor_id}（mobile={mobile or '-'}, email={email or '-'}）"
        )

    def send_interactive_card(self, open_id: str, card: dict[str, Any]) -> str:
        url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id"
        payload = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            raise FeishuApiError(
                f"发送飞书消息失败: {data.get('msg') or resp.text}。"
                f"请确认应用已开通 im:message 且目标用户已与机器人建立会话（或开通单聊权限）",
                code=data.get("code"),
            )
        return str((data.get("data") or {}).get("message_id") or "")

    def probe_credentials(self) -> dict[str, Any]:
        """连通性探测：仅验证能否拿到 token。"""
        token = self.tenant_access_token(force_refresh=True)
        return {"ok": True, "token_prefix": token[:8] + "…"}
