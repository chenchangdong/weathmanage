"""API route handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from agent_core.explain_agent import ExplainAgent
from api.schemas import (
    AllocationReportExportRequest,
    AdvisorChatRequest,
    AutoRebalanceRequest,
    FlagCategorySuggestRequest,
    ManualAdjustRequest,
    ModelDeleteRequest,
    ModelSaveRequest,
    PortfolioMapSaveRequest,
    SopAgentQueryRequest,
    SopAgentRunRequest,
    SopAgentRunBatchRequest,
    SopAgentPushBatchRequest,
    SopAgentPushRequest,
    SopAdvisorResolveRequest,
    SopAdvisorSyncRequest,
    SopBatchScheduleSaveRequest,
    SopEventCleanupRequest,
    SopRunBatchRequest,
    SopSystemSaveRequest,
)
from agent_core.advisor_chat import AdvisorChatService
from core.allocation_config_service import AllocationConfigService
from core.config_loader import (
    get_category_names,
    get_customer_risk_levels,
    get_demo_customer,
    get_product_map,
    get_products_for_display_category,
    get_risk_level_name,
    is_product_limit_validation_enabled,
    load_customer_profile,
    load_model_config,
    load_portfolio_mapping,
    load_sop_rule_system,
)
from core.config_writer import (
    delete_model,
    save_model_config,
    save_portfolio_mapping,
    save_sop_rule_system,
    save_sop_agent_batch_schedule,
)
from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine
from core.config_loader import load_sop_agent_system
from core.sop_agent_service import SopAgentService
from core.sop_rule_engine import SopRuleEngine
from core.sop_event_store import SopEventStore
from core.asset_service import AssetOverviewService, overview_to_dict
from core.data_store import get_customer_holdings
from core.product_display import apply_demand_deposit_to_result
from core.allocation_report_ppt import (
    REPORT_CHAPTERS,
    build_allocation_report_ppt,
    content_disposition_attachment,
    normalize_chapters,
    report_filename,
)
from core.wealth_journey_service import (
    WealthJourneyService,
    effective_personalized_flags,
    personalized_allocation_block_message,
)

router = APIRouter(prefix="/api")


def _rebalance_to_dict(result) -> Dict[str, Any]:
    pmap = get_product_map()
    return {
        "customer_id": result.customer_id,
        "risk_profile": result.risk_profile,
        "risk_profile_name": get_risk_level_name(result.risk_profile),
        "total_assets": result.total_assets,
        "idle_cash": result.idle_cash,
        "mode": result.mode,
        "locked_categories": result.locked_categories,
        "category_summary": result.category_summary,
        "category_targets": result.category_targets,
        "product_deltas": [
            {
                "product_code": d.product_code,
                "product_name": d.product_name,
                "category": d.category,
                "asset_type": pmap.get(d.product_code, {}).get("asset_type"),
                "asset_type_name": pmap.get(d.product_code, {}).get("asset_type_name"),
                "min_amount": pmap.get(d.product_code, {}).get("min_amount", 0),
                "max_amount": pmap.get(d.product_code, {}).get("max_amount"),
                "current_amount": d.current_amount,
                "target_amount": d.target_amount,
                "delta_amount": d.delta_amount,
                "action": d.action,
                "limit_hit": d.limit_hit,
                "limit_side": d.limit_side,
            }
            for d in result.product_deltas
        ],
        "validation_notes": result.validation_notes,
        "view_mode": result.view_mode,
        "product_category": result.product_category,
    }


@router.get("/customer/list")
def list_customers() -> Dict[str, Any]:
    """演示客户列表（含五档风险等级）。"""
    customers = []
    for c in load_customer_profile().get("demo_customers", []):
        risk = c.get("risk_profile", "")
        customers.append({
            **c,
            "risk_profile_name": get_risk_level_name(risk),
        })
    return {"code": 0, "message": "ok", "data": {"customers": customers}}


@router.get("/risk/levels")
def list_risk_levels() -> Dict[str, Any]:
    """五档客户风险 ↔ 投资组合偏好映射说明。"""
    svc = AllocationConfigService()
    mapping = load_portfolio_mapping()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "levels": get_customer_risk_levels(),
            "risk_customer_map": mapping.get("risk_customer_map", {}),
            "risk_loss_default": mapping.get("risk_loss_default", {}),
        },
    }


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "four-money-advisor"}


@router.get("/asset/overview")
def get_asset_overview(
    customer_id: str = Query(..., description="客户ID"),
    role: str = Query("advisor", description="角色 advisor/viewer"),
    product_category: Optional[str] = Query(
        None, description="规划类型：投资规划 / 综合规划"
    ),
    loss_key: Optional[str] = Query(
        None, description="投资组合偏好档位，覆盖客户风险默认模型"
    ),
) -> Dict[str, Any]:
    """查询客户首页卡片数据。"""
    try:
        service = AssetOverviewService()
        overview = service.build_overview(
            customer_id, role, product_category=product_category, loss_key=loss_key
        )
        return {"code": 0, "message": "ok", "data": overview_to_dict(overview)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/wealth/inventory")
def wealth_inventory() -> Dict[str, Any]:
    """财富盘点：客户列表 + 场景化财富健康标志。"""
    svc = WealthJourneyService()
    return {"code": 0, "message": "ok", "data": {"customers": svc.build_inventory()}}


@router.get("/wealth/diagnosis")
def wealth_diagnosis(
    customer_id: str = Query(..., description="客户ID"),
) -> Dict[str, Any]:
    """资产诊断：单客户结构化诊断结果。"""
    try:
        svc = WealthJourneyService()
        return {"code": 0, "message": "ok", "data": svc.build_diagnosis(customer_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/allocation/auto_rebalance")
def auto_rebalance(req: AutoRebalanceRequest) -> Dict[str, Any]:
    """一键智能算配置方案。"""
    customer = get_demo_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {req.customer_id}")

    data = get_customer_holdings(req.customer_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"No holdings: {req.customer_id}")

    holdings = req.holdings or data["holdings"]
    idle_cash = req.idle_cash if req.idle_cash is not None else 0.0

    product_category = req.product_category or customer.get("product_category", "投资规划")

    flag_codes: list[str] | None = None
    if req.mode in ("flag_personalized", "optimal_personalized"):
        if product_category != "投资规划":
            raise HTTPException(
                status_code=400,
                detail="个性化智能配仓仅支持投资规划",
            )
    if req.mode == "flag_personalized":
        svc = WealthJourneyService()
        try:
            diagnosis = svc.build_diagnosis(req.customer_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        flag_codes = [
            f["code"] for f in effective_personalized_flags(diagnosis.get("flags", []))
        ]
        block_msg = personalized_allocation_block_message(diagnosis.get("flags", []))
        if block_msg:
            raise HTTPException(
                status_code=400,
                detail=block_msg,
            )

    engine = AutoRebalanceEngine()
    try:
        result = engine.rebalance(
            customer_id=req.customer_id,
            holdings=holdings,
            idle_cash=idle_cash,
            risk_profile=customer["risk_profile"],
            mode=req.mode,
            locked_categories=req.locked_categories,
            manual_overrides=req.manual_overrides,
            target_category=req.target_category,
            product_category=product_category,
            flag_codes=flag_codes,
            loss_key=req.loss_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    apply_demand_deposit_to_result(result, holdings)
    explain = ExplainAgent().generate(result)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "rebalance": _rebalance_to_dict(result),
            "explanation": explain,
        },
    }


@router.get("/allocation/page_constraints")
def allocation_page_constraints() -> Dict[str, Any]:
    """前端页面约束（如是否启用产品上下限校验）。"""
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "product_limit_validation_enabled": is_product_limit_validation_enabled(),
        },
    }


@router.get("/products/candidates")
def list_product_candidates(
    category: str = Query(
        ...,
        description="卡片 category：四笔钱 spend/preserve/grow/protect，或资产类型 cash/fixed_income/equity/alternative",
    ),
) -> Dict[str, Any]:
    """查询指定大类的候选产品列表（二次调仓产品选择）。"""
    products_raw, names = get_products_for_display_category(category)
    if category not in names and not products_raw:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category}")
    products = [
        {
            "code": p["code"],
            "name": p["name"],
            "category": category,
            "category_name": names.get(category, category),
            "asset_type": p.get("asset_type"),
            "asset_type_name": p.get("asset_type_name"),
            "min_amount": p.get("min_amount", 0),
            "max_amount": p.get("max_amount"),
            "rebalance_priority": p.get("rebalance_priority", 3),
            "risk_level": p.get("risk_level"),
        }
        for p in products_raw
    ]
    return {"code": 0, "message": "ok", "data": {"category": category, "products": products}}


@router.get("/products/ai_recommend")
def ai_recommend_products(
    customer_id: str = Query(..., description="客户 ID"),
    category: str = Query(..., description="卡片 category（同 candidates 接口）"),
    exclude: str = Query("", description="排除的产品 code，逗号分隔（已在方案明细中的产品）"),
) -> Dict[str, Any]:
    """AI 智能选品（模拟）：推荐 risk_level 最接近客户风险档位、且未持仓的产品，最多 2 款。"""
    from core.product_recommend_service import ProductRecommendService

    exclude_codes = [c.strip() for c in exclude.split(",") if c.strip()]
    svc = ProductRecommendService()
    try:
        result = svc.recommend(
            customer_id=customer_id,
            category=category,
            exclude_codes=exclude_codes,
            max_count=2,
        )
    except ValueError as e:
        msg = str(e)
        if "Customer not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=404, detail=msg) from e

    return {"code": 0, "message": "ok", "data": result}


@router.post("/allocation/manual_adjust")
def manual_adjust(req: ManualAdjustRequest) -> Dict[str, Any]:
    """人工二次调整产品目标，联动重算大类占比与区间校验。"""
    customer = get_demo_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {req.customer_id}")

    data = get_customer_holdings(req.customer_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"No holdings: {req.customer_id}")

    holdings = req.holdings or data["holdings"]
    idle_cash = req.idle_cash if req.idle_cash is not None else 0.0
    product_category = req.product_category or customer.get("product_category", "投资规划")

    engine = AutoRebalanceEngine()
    try:
        result = engine.apply_manual_product_targets(
            customer_id=req.customer_id,
            holdings=holdings,
            idle_cash=idle_cash,
            risk_profile=customer["risk_profile"],
            product_targets=req.product_targets,
            baseline_product_targets=req.baseline_product_targets,
            product_category=product_category,
            loss_key=req.loss_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    apply_demand_deposit_to_result(result, holdings)
    explain = ExplainAgent().generate(result)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "rebalance": _rebalance_to_dict(result),
            "explanation": explain,
        },
    }


@router.post("/allocation/flag_category_suggest")
def flag_category_suggest(req: FlagCategorySuggestRequest) -> Dict[str, Any]:
    """个性化配仓：单个大类产品层智能建议（参考分配，不改动大类处方）。"""
    customer = get_demo_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {req.customer_id}")

    product_category = req.product_category or customer.get("product_category", "投资规划")
    if product_category != "投资规划":
        raise HTTPException(status_code=400, detail="个性化配仓仅支持投资规划")

    data = get_customer_holdings(req.customer_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"No holdings: {req.customer_id}")

    holdings = req.holdings or data["holdings"]
    engine = AutoRebalanceEngine()
    try:
        cat_deltas, notes = engine.suggest_flag_category_products(
            holdings=holdings,
            category=req.category,
            category_targets=req.category_targets,
            baseline_product_targets=req.baseline_product_targets,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    pmap = get_product_map()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "category": req.category,
            "product_deltas": [
                {
                    "product_code": d.product_code,
                    "product_name": d.product_name,
                    "category": d.category,
                    "min_amount": pmap.get(d.product_code, {}).get("min_amount", 0),
                    "max_amount": pmap.get(d.product_code, {}).get("max_amount"),
                    "current_amount": d.current_amount,
                    "target_amount": d.target_amount,
                    "delta_amount": d.delta_amount,
                    "action": d.action,
                    "limit_hit": d.limit_hit,
                    "limit_side": d.limit_side,
                }
                for d in cat_deltas
            ],
            "notes": notes,
        },
    }


@router.get("/model/list")
def list_models() -> Dict[str, Any]:
    """页面A：模型列表。"""
    cfg = load_model_config()
    svc = AllocationConfigService()
    models = []
    for code in svc.list_models():
        m = cfg["model_list"][code]
        models.append({
            "model_code": code,
            "model_name": m.get("model_name", code),
            "expect_annual_return": m.get("expect_annual_return"),
            "expect_volatility": m.get("expect_volatility"),
            "asset_limit": m.get("asset_limit", {}),
        })
    return {"code": 0, "message": "ok", "data": {"models": models}}


@router.get("/model/detail")
def get_model_detail(model_code: str = Query(...)) -> Dict[str, Any]:
    """页面A：单模型详情（含四笔钱聚合阈值）。"""
    try:
        svc = AllocationConfigService()
        return {"code": 0, "message": "ok", "data": svc.get_model_detail(model_code)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/model/delete-check")
def model_delete_check(model_code: str = Query(...)) -> Dict[str, Any]:
    """删除前检查：是否被风险映射引用。"""
    svc = AllocationConfigService()
    refs = svc.find_model_portfolio_refs(model_code.strip())
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "model_code": model_code,
            "deletable": len(refs) == 0,
            "mapping_refs": refs,
        },
    }


@router.post("/model/delete")
def remove_model(req: ModelDeleteRequest) -> Dict[str, Any]:
    """删除资产配置模型（无风险映射引用时）。"""
    code = req.model_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="model_code 不能为空")
    svc = AllocationConfigService()
    refs = svc.find_model_portfolio_refs(code)
    if refs:
        labels = "、".join(
            f"{r['product_category']}/{r.get('loss_label') or r['loss_key']}"
            for r in refs
        )
        raise HTTPException(
            status_code=400,
            detail=f"该模型已被风险映射引用（{labels}），请先在页面B解除映射后再删除",
        )
    try:
        delete_model(code)
        return {"code": 0, "message": "删除成功", "data": {"model_code": code}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/model/save")
def save_model(req: ModelSaveRequest) -> Dict[str, Any]:
    """页面A保存 → model_config.yaml"""
    try:
        if not req.model_list:
            raise ValueError("model_list 不能为空")
        renames = [
            {"from": r.from_code, "to": r.to_code}
            for r in req.code_renames
            if r.from_code.strip() and r.to_code.strip()
        ]
        for item in renames:
            if item["from"] not in req.model_list and item["to"] in req.model_list:
                pass  # 已用新编码写入 model_list
            elif item["to"] in req.model_list and item["from"] != item["to"]:
                others = [k for k in req.model_list if k != item["from"]]
                if item["to"] in others:
                    raise ValueError(f"模型编码已存在: {item['to']}")
        svc = AllocationConfigService()
        for code, model in req.model_list.items():
            asset_limit = model.get("asset_limit") or {}
            label = model.get("model_name") or code
            svc.validate_four_money_benchmark_sum(asset_limit, model_label=label)
        save_model_config(req.model_list, code_renames=renames)
        return {"code": 0, "message": "保存成功", "data": {"count": len(req.model_list)}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/portfolio/map")
def get_portfolio_map(
    product_category: Optional[str] = Query(None, description="筛选：投资规划"),
) -> Dict[str, Any]:
    """页面B：映射表数据。"""
    mapping = load_portfolio_mapping()
    svc = AllocationConfigService()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "rows": svc.get_portfolio_map_table(product_category),
            "risk_customer_map": mapping.get("risk_customer_map", {}),
            "risk_loss_default": mapping.get("risk_loss_default", {}),
            "customer_risk_levels": mapping.get("customer_risk_levels", []),
            "model_list": svc.list_models(),
        },
    }


@router.post("/portfolio/map/save")
def save_portfolio_map(req: PortfolioMapSaveRequest) -> Dict[str, Any]:
    """页面B保存 → portfolio_mapping.yaml"""
    try:
        save_portfolio_mapping(
            req.portfolio_map,
            risk_customer_map=req.risk_customer_map,
            risk_loss_default=req.risk_loss_default,
            customer_risk_levels=req.customer_risk_levels,
        )
        return {"code": 0, "message": "保存成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/allocation/resolve")
def resolve_allocation(
    product_category: str = Query("投资规划"),
    risk_label: str = Query(
        ...,
        description="conservative/prudent/balanced/growth/aggressive",
    ),
) -> Dict[str, Any]:
    """调试：客户风险 → 模型 → 四笔钱阈值完整链路。"""
    try:
        svc = AllocationConfigService()
        data = svc.resolve_profile_targets(product_category, risk_label)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ai/status")
def ai_status() -> Dict[str, Any]:
    """大模型接入状态（是否已配置 API Key）。"""
    svc = AdvisorChatService()
    return {"code": 0, "message": "ok", "data": svc.status()}


@router.post("/ai/chat")
def advisor_chat(req: AdvisorChatRequest) -> Dict[str, Any]:
    """理财经理 AI 顾问对话（基于资产检视/配置方案 grounding）。"""
    customer = get_demo_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {req.customer_id}")

    svc = AdvisorChatService()
    try:
        result = svc.chat(
            customer_id=req.customer_id,
            message=req.message,
            history=[h.model_dump() for h in req.history],
            overview=req.overview,
            plan=req.plan,
            diagnosis=req.diagnosis,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"code": 0, "message": "ok", "data": result}


@router.post("/ai/chat/stream")
def advisor_chat_stream(req: AdvisorChatRequest) -> StreamingResponse:
    """理财经理 AI 顾问对话（SSE 流式，实时推送思考过程）。"""
    import json

    customer = get_demo_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {req.customer_id}")

    svc = AdvisorChatService()

    def event_stream():
        try:
            for chunk in svc.chat_stream(
                customer_id=req.customer_id,
                message=req.message,
                history=[h.model_dump() for h in req.history],
                overview=req.overview,
                plan=req.plan,
                diagnosis=req.diagnosis,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except ValueError as e:
            payload = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/allocation/report_chapters")
def list_report_chapters() -> Dict[str, Any]:
    """资产配置报告可选章节列表。"""
    return {"code": 0, "message": "ok", "data": {"chapters": REPORT_CHAPTERS}}


@router.post("/allocation/export_report_ppt")
def export_allocation_report_ppt(req: AllocationReportExportRequest):
    """导出资产配置报告 PPT（封面 + 目录 + 章节空白页）。"""
    customer = get_demo_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {req.customer_id}")

    chapters = normalize_chapters(req.chapters)
    if not chapters:
        raise HTTPException(status_code=400, detail="请至少选择一个有效章节")

    try:
        content = build_allocation_report_ppt(
            customer_name=customer.get("name") or req.customer_id,
            selected_chapters=chapters,
            branch_name=req.branch_name or "--",
            advisor_name=req.advisor_name or "--",
            contact_phone=req.contact_phone or "--",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    filename = report_filename(customer.get("name") or req.customer_id)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": content_disposition_attachment(filename),
        },
    )


# ── SOP 6.1 / 6.2（独立于投后陪伴）────────────────────────────────────────


@router.get("/sop/system")
def get_sop_system_config() -> Dict[str, Any]:
    return {"code": 0, "message": "ok", "data": load_sop_rule_system()}


@router.post("/sop/system")
def save_sop_system_config(req: SopSystemSaveRequest) -> Dict[str, Any]:
    try:
        save_sop_rule_system(req.config, version=req.version)
        return {"code": 0, "message": "ok", "data": load_sop_rule_system()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/sop/events/stats")
def sop_events_stats() -> Dict[str, Any]:
    store = SopEventStore()
    return {"code": 0, "message": "ok", "data": store.stats()}


@router.post("/sop/events/run-batch")
def sop_run_batch(req: SopRunBatchRequest = SopRunBatchRequest()) -> Dict[str, Any]:
    """6.1.2 事件触发跑批（模拟每日扫描）。"""
    from datetime import date

    as_of = None
    if req.as_of:
        as_of = date.fromisoformat(req.as_of[:10])
    engine = SopRuleEngine()
    engine.reload()
    result = engine.run_batch(as_of=as_of, replace=req.replace)
    return {"code": 0, "message": "ok", "data": result}


@router.post("/sop/events/cleanup")
def sop_events_cleanup(req: SopEventCleanupRequest = SopEventCleanupRequest()) -> Dict[str, Any]:
    """清理历史：clear_all 清空全部；否则删除 data_date 早于 N 天前的记录（默认 7 天）。"""
    from datetime import date, timedelta

    store = SopEventStore()
    if req.clear_all:
        removed = store.purge_all()
        return {
            "code": 0,
            "message": "ok",
            "data": {"mode": "all", "removed": removed},
        }
    days = req.retention_days if req.retention_days is not None else 7
    cutoff = date.today() - timedelta(days=days)
    removed = store.cleanup_before(cutoff)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "mode": "days_ago",
            "retention_days": days,
            "cutoff_before": cutoff.isoformat(),
            "removed": removed,
        },
    }


@router.post("/sop/events/dedupe")
def sop_events_dedupe() -> Dict[str, Any]:
    """合并库内重复事件（同 data_date + 产品 + 组合事件/规则）。"""
    store = SopEventStore()
    removed = store.dedupe_all()
    return {"code": 0, "message": "ok", "data": {"removed": removed}}


@router.get("/sop/rule-logs")
def sop_rule_logs(
    business_type: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> Dict[str, Any]:
    store = SopEventStore()
    rows = store.list_rule_logs(business_type=business_type, limit=limit)
    return {"code": 0, "message": "ok", "data": {"logs": rows}}


@router.get("/sop/events")
def sop_list_events(
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    big_class: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    drawdown_only: bool = Query(False),
    composite_code: Optional[str] = Query(None),
) -> Dict[str, Any]:
    engine = SopRuleEngine()
    events = engine.query_events(
        since=since,
        until=until,
        big_class=big_class,
        keyword=keyword,
        drawdown_only=drawdown_only,
        composite_code=composite_code,
    )
    return {"code": 0, "message": "ok", "data": {"events": events, "total": len(events)}}


@router.post("/sop/agent/query")
def sop_agent_query(req: SopAgentQueryRequest) -> Dict[str, Any]:
    """6.2 自然语言查询事件（演示）。"""
    svc = SopAgentService()
    data = svc.query_and_summarize(
        req.question,
        since=req.since,
        drawdown_only=req.drawdown_only,
    )
    return {"code": 0, "message": "ok", "data": data}


@router.post("/sop/agent/run")
def sop_agent_run(req: SopAgentRunRequest) -> Dict[str, Any]:
    """6.2 对指定事件运行投后智能体。"""
    try:
        data = SopAgentService().run_for_event(req.event_id)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/sop/agent/output")
def sop_agent_output(event_id: str = Query(...)) -> Dict[str, Any]:
    output = SopEventStore().get_agent_output(event_id)
    if not output:
        raise HTTPException(status_code=404, detail=f"未找到智能体输出: {event_id}")
    return {"code": 0, "message": "ok", "data": output}


@router.get("/sop/agent/config")
def sop_agent_config() -> Dict[str, Any]:
    """6.2 智能体配置（模板、调度、数据源降级说明）。"""
    return {"code": 0, "message": "ok", "data": load_sop_agent_system()}


@router.get("/sop/agent/schedule/status")
def sop_agent_schedule_status() -> Dict[str, Any]:
    from core.sop_batch_scheduler import get_scheduler_status

    return {"code": 0, "message": "ok", "data": get_scheduler_status()}


@router.get("/sop/agent/schedule/triggers")
def sop_agent_schedule_triggers() -> Dict[str, Any]:
    """触发管理列表（当前仅投后 SOP 事件跑批）。"""
    from core.sop_batch_scheduler import get_scheduler_status

    status = get_scheduler_status()
    trigger = {
        "id": "sop_event_batch",
        "trigger_name": status.get("trigger_name"),
        "trigger_type": status.get("trigger_type", "CRON"),
        "cron": status.get("cron"),
        "cron_label": status.get("cron_label"),
        "description": status.get("description"),
        "enabled": status.get("enabled"),
        "hour": status.get("hour"),
        "minute": status.get("minute"),
        "run_agent_after_batch": status.get("run_agent_after_batch"),
        "push_feishu_after_agent": status.get("push_feishu_after_agent"),
        "last_trigger_time": status.get("last_trigger_time"),
        "last_batch_date": status.get("last_batch_date"),
        "next_run_hint": status.get("next_run_hint"),
        "action_label": _batch_action_label(status),
    }
    return {"code": 0, "message": "ok", "data": {"triggers": [trigger]}}


def _batch_action_label(status: dict[str, Any]) -> str:
    parts = ["6.1 事件跑批"]
    if status.get("run_agent_after_batch"):
        parts.append("6.2 智能生成")
        if status.get("push_feishu_after_agent"):
            parts.append("飞书推送")
    return " + ".join(parts)


@router.put("/sop/agent/schedule/config")
def sop_agent_schedule_config(req: SopBatchScheduleSaveRequest) -> Dict[str, Any]:
    """保存定时跑批配置并确保调度线程运行。"""
    from core.sop_batch_scheduler import ensure_scheduler_running, get_scheduler_status

    save_sop_agent_batch_schedule(req.model_dump())
    ensure_scheduler_running()
    return {"code": 0, "message": "ok", "data": get_scheduler_status()}


@router.post("/sop/agent/run-batch")
def sop_agent_run_batch(req: SopAgentRunBatchRequest = SopAgentRunBatchRequest()) -> Dict[str, Any]:
    """6.2 批量运行智能体管道（pending 或指定 event_ids，默认每批 20 条）。"""
    svc = SopAgentService()
    limit = max(1, min(req.limit, 100))
    use_llm = bool(req.use_llm)
    if req.event_ids:
        data = svc.run_batch_for_events(req.event_ids, limit=limit, use_llm=use_llm)
    elif req.all_pending:
        data = svc.run_batch_for_events(None, limit=limit, use_llm=use_llm)
    else:
        data = svc.run_batch_for_events(None, limit=limit, use_llm=use_llm)
    return {"code": 0, "message": "ok", "data": data}


@router.post("/sop/events/scheduled-batch")
def sop_scheduled_batch(force: bool = Query(False)) -> Dict[str, Any]:
    """手动触发定时跑批（6.1 + 可选 6.2）。"""
    from core.sop_batch_scheduler import run_scheduled_batch

    return {"code": 0, "message": "ok", "data": run_scheduled_batch(force=force)}


@router.get("/sop/agent/push/preview")
def sop_agent_push_preview(event_id: str = Query(...)) -> Dict[str, Any]:
    """6.2.5 预览：事件将推送给哪些客户经理（按持有客户拆分，不聚合）。"""
    from core.sop_push_service import SopPushService

    try:
        data = SopPushService().preview_event(event_id)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/sop/agent/push")
def sop_agent_push(req: SopAgentPushRequest) -> Dict[str, Any]:
    """6.2.5 对单条事件向各持有客户的客户经理发送飞书私聊（每人一条，不聚合）。"""
    from core.sop_push_service import SopPushService

    try:
        data = SopPushService().push_event(req.event_id, force=req.force)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sop/agent/push-batch")
def sop_agent_push_batch(req: SopAgentPushBatchRequest = SopAgentPushBatchRequest()) -> Dict[str, Any]:
    """6.2.5 批量推送已完成智能体输出且未成功推送的事件。"""
    from core.sop_push_service import SopPushService

    data = SopPushService().push_batch(
        req.event_ids,
        all_done_unpushed=req.all_done_unpushed,
        limit=max(1, min(req.limit, 50)),
        force=req.force,
    )
    return {"code": 0, "message": "ok", "data": data}


@router.post("/sop/agent/feishu/sync-advisors")
def sop_feishu_sync_advisors(req: SopAdvisorSyncRequest = SopAdvisorSyncRequest()) -> Dict[str, Any]:
    """
    批量对齐全部客户经理飞书 open_id（写入 data/advisor_feishu_cache.json）。
    经理名录只需 mobile/email/employee_no，无需手工配置 open_id。
    """
    from core.sop_feishu_client import FeishuApiError
    from core.sop_push_service import SopPushService

    try:
        data = SopPushService().sync_advisors(force=req.force)
        return {"code": 0, "message": "ok", "data": data}
    except FeishuApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/sop/agent/feishu/advisor-cache")
def sop_feishu_advisor_cache() -> Dict[str, Any]:
    """查看已缓存的客户经理 open_id。"""
    from core.advisor_feishu_cache import AdvisorFeishuCache

    cache = AdvisorFeishuCache().list_all()
    return {"code": 0, "message": "ok", "data": {"count": len(cache), "advisors": cache}}


@router.post("/sop/agent/feishu/resolve-advisor")
def sop_feishu_resolve_advisor(req: SopAdvisorResolveRequest) -> Dict[str, Any]:
    """
    用手机号/邮箱向飞书换取客户经理 open_id（首次配置用）。
    换取成功后建议写入 config/advisor_directory.yaml 的 feishu_open_id。
    """
    from core.sop_feishu_client import FeishuApiError
    from core.sop_push_service import SopPushService

    try:
        data = SopPushService().resolve_advisor_open_id(req.advisor_id)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FeishuApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/sop/agent/feishu/probe")
def sop_feishu_probe() -> Dict[str, Any]:
    """探测飞书应用凭证是否可用。"""
    from core.sop_feishu_client import FeishuApiError
    from core.sop_push_service import SopPushService

    try:
        data = SopPushService().probe()
        return {"code": 0, "message": "ok", "data": data}
    except FeishuApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
