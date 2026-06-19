"""规则策略 API — 对齐 wealthlive.com.cn:8005 /api/rule/* 与 /api/rules/*。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.rule_system_service import RuleSystemService

rule_router = APIRouter()
_svc = RuleSystemService()


class RuleConfigBody(BaseModel):
    rule_code: str
    rule_name: str
    rule_expr: str
    biz_type: str = "product_drawdown"
    status: int = 1
    short_circuit: int = 1
    remark: str = ""


class MetricBody(BaseModel):
    metric_code: str
    metric_name: str
    biz_type: str = "product_drawdown"
    value_field: str
    remark: str = ""


class BizTypeBody(BaseModel):
    code: str
    name: str
    remark: str = ""
    sort: int = 0
    status: int = 1
    short_circuit: int = 1


class ExecuteBody(BaseModel):
    bizType: str
    bizNo: str
    data: Dict[str, Any] = Field(default_factory=dict)


class TestBody(BaseModel):
    expr: str
    test_data: Dict[str, Any] = Field(default_factory=dict)


# ── 规则配置 ─────────────────────────────────────────────────


@rule_router.get("/api/rule/config/list")
def rule_config_list() -> List[Dict[str, Any]]:
    return _svc.list_rules()


@rule_router.post("/api/rule/config/add")
def rule_config_add(body: RuleConfigBody) -> Dict[str, Any]:
    return _svc.add_rule(body.model_dump())


@rule_router.put("/api/rule/config/{rule_id}")
def rule_config_update(rule_id: int, body: RuleConfigBody) -> Dict[str, Any]:
    row = _svc.update_rule(rule_id, body.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    return row


@rule_router.delete("/api/rule/config/{rule_id}")
def rule_config_delete(rule_id: int) -> Dict[str, str]:
    if not _svc.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": "true"}


@rule_router.post("/api/rule/config/{rule_id}/enable")
def rule_config_enable(rule_id: int) -> Dict[str, Any]:
    row = _svc.toggle_rule(rule_id, True)
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    return row


@rule_router.post("/api/rule/config/{rule_id}/disable")
def rule_config_disable(rule_id: int) -> Dict[str, Any]:
    row = _svc.toggle_rule(rule_id, False)
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    return row


# ── 指标 ─────────────────────────────────────────────────────


@rule_router.get("/api/rule/metric/list")
def metric_list() -> List[Dict[str, Any]]:
    return _svc.list_metrics()


@rule_router.post("/api/rule/metric/add")
def metric_add(body: MetricBody) -> Dict[str, Any]:
    return _svc.add_metric(body.model_dump())


@rule_router.delete("/api/rule/metric/{metric_id}")
def metric_delete(metric_id: int) -> Dict[str, str]:
    if not _svc.delete_metric(metric_id):
        raise HTTPException(status_code=404, detail="指标不存在")
    return {"ok": "true"}


# ── 规则分组 ─────────────────────────────────────────────────


@rule_router.get("/api/rule/biz-type/list")
def biz_type_list(include_disabled: bool = Query(False)) -> List[Dict[str, Any]]:
    return _svc.list_biz_types(include_disabled=include_disabled)


@rule_router.post("/api/rule/biz-type/add")
def biz_type_add(body: BizTypeBody) -> Dict[str, Any]:
    return _svc.add_biz_type(body.model_dump())


@rule_router.put("/api/rule/biz-type/{bid}")
def biz_type_update(bid: int, body: BizTypeBody) -> Dict[str, Any]:
    row = _svc.update_biz_type(bid, body.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="分组不存在")
    return row


@rule_router.delete("/api/rule/biz-type/{bid}")
def biz_type_delete(bid: int) -> Dict[str, str]:
    if not _svc.delete_biz_type(bid):
        raise HTTPException(status_code=404, detail="分组不存在")
    return {"ok": "true"}


# ── 事件日志 ─────────────────────────────────────────────────


@rule_router.get("/api/rule/event/list")
def event_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    biz_type: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _svc.list_events(page=page, page_size=page_size, biz_type=biz_type)


@rule_router.get("/api/rule/run-detail/list")
def run_detail_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    biz_type: Optional[str] = Query(None),
    is_hit: Optional[str] = Query(None),
    rule_code: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _svc.list_run_details(
        page=page,
        page_size=page_size,
        biz_type=biz_type,
        is_hit=is_hit,
        rule_code=rule_code,
    )


# ── 执行 / 测试 ──────────────────────────────────────────────


@rule_router.post("/api/rule/execute")
def rule_execute(body: ExecuteBody) -> Dict[str, Any]:
    return _svc.execute_rules(body.bizType, body.bizNo, body.data)


@rule_router.post("/api/rule/test")
def rule_test(body: TestBody) -> Dict[str, Any]:
    return _svc.test_expression(body.expr, body.test_data)


# ── 出入配置 ─────────────────────────────────────────────────


@rule_router.get("/api/rules/trigger")
def io_trigger_list() -> List[Dict[str, Any]]:
    return _svc.list_io_triggers()


@rule_router.post("/api/rules/trigger")
async def io_trigger_add(request: Dict[str, Any]) -> Dict[str, Any]:
    return _svc.save_io_trigger(request)


@rule_router.put("/api/rules/trigger/{tid}")
async def io_trigger_update(tid: int, request: Dict[str, Any]) -> Dict[str, Any]:
    row = _svc.save_io_trigger(request, tid=tid)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    return row


@rule_router.delete("/api/rules/trigger/{tid}")
def io_trigger_delete(tid: int) -> Dict[str, str]:
    if not _svc.delete_io_trigger(tid):
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"ok": "true"}


@rule_router.get("/api/rules/action")
def io_action_list() -> List[Dict[str, Any]]:
    return _svc.list_io_actions()


@rule_router.post("/api/rules/action")
async def io_action_add(request: Dict[str, Any]) -> Dict[str, Any]:
    return _svc.save_io_action(request)


@rule_router.put("/api/rules/action/{aid}")
async def io_action_update(aid: int, request: Dict[str, Any]) -> Dict[str, Any]:
    row = _svc.save_io_action(request, aid=aid)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    return row


@rule_router.delete("/api/rules/action/{aid}")
def io_action_delete(aid: int) -> Dict[str, str]:
    if not _svc.delete_io_action(aid):
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"ok": "true"}
