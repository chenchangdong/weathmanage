"""API route handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from agent_core.explain_agent import ExplainAgent
from api.schemas import (
    AdvisorChatRequest,
    AftercareCompanionRequest,
    AftercareItemGenerateRequest,
    AftercareSystemSaveRequest,
    AutoRebalanceRequest,
    ManualAdjustRequest,
    ModelDeleteRequest,
    ModelSaveRequest,
    PortfolioMapSaveRequest,
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
    load_aftercare_system,
    load_customer_profile,
    load_model_config,
    load_portfolio_mapping,
)
from core.config_writer import (
    delete_model,
    save_aftercare_system,
    save_model_config,
    save_portfolio_mapping,
)
from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine
from core.aftercare_companion_service import AftercareCompanionService
from core.aftercare_monitor_service import AftercareMonitorService
from core.asset_service import AssetOverviewService, overview_to_dict
from core.data_store import get_customer_holdings
from core.wealth_journey_service import WealthJourneyService

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
) -> Dict[str, Any]:
    """查询客户首页卡片数据。"""
    try:
        service = AssetOverviewService()
        overview = service.build_overview(
            customer_id, role, product_category=product_category
        )
        return {"code": 0, "message": "ok", "data": overview_to_dict(overview)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/wealth/inventory")
def wealth_inventory() -> Dict[str, Any]:
    """财富盘点：客户列表 + 场景化健康标志。"""
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
    idle_cash = req.idle_cash if req.idle_cash is not None else data["idle_cash"]

    product_category = req.product_category or customer.get("product_category", "投资规划")

    flag_codes: list[str] | None = None
    if req.mode == "flag_personalized":
        if product_category != "投资规划":
            raise HTTPException(
                status_code=400,
                detail="个性化智能配仓仅支持投资规划",
            )
        svc = WealthJourneyService()
        try:
            diagnosis = svc.build_diagnosis(req.customer_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        flag_codes = [
            f["code"]
            for f in diagnosis.get("flags", [])
            if f.get("code") != "four_money_mismatch"
        ]
        if not flag_codes:
            raise HTTPException(
                status_code=400,
                detail="财富健康，请用全账户一键配仓",
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    idle_cash = req.idle_cash if req.idle_cash is not None else data["idle_cash"]
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    explain = ExplainAgent().generate(result)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "rebalance": _rebalance_to_dict(result),
            "explanation": explain,
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


@router.get("/aftercare/system")
def get_aftercare_system_config() -> Dict[str, Any]:
    """读取投后陪伴体系配置。"""
    return {"code": 0, "message": "ok", "data": load_aftercare_system()}


@router.post("/aftercare/system")
def save_aftercare_system_config(req: AftercareSystemSaveRequest) -> Dict[str, Any]:
    """保存投后陪伴体系配置。"""
    try:
        save_aftercare_system(req.config, version=req.version)
        return {"code": 0, "message": "ok", "data": load_aftercare_system()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/aftercare/monitor")
def get_aftercare_monitor(
    customer_id: str = Query(..., description="客户ID"),
) -> Dict[str, Any]:
    """模拟当日投研/产品监测预警（不含话术生成）。"""
    try:
        data = AftercareMonitorService().detect_all(customer_id)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/aftercare/companion/generate")
def generate_aftercare_companion(req: AftercareCompanionRequest) -> Dict[str, Any]:
    """根据当日监测预警生成应对策略与客户沟通话术（非流式）。"""
    try:
        data = AftercareCompanionService().generate(req.customer_id)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/aftercare/companion/generate/stream")
def generate_aftercare_companion_stream(req: AftercareCompanionRequest) -> StreamingResponse:
    """流式生成每条预警的应对策略与客户沟通话术。"""
    import json

    svc = AftercareCompanionService()

    def event_stream():
        try:
            for chunk in svc.generate_stream(req.customer_id):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except ValueError as e:
            payload = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/aftercare/companion/generate/item")
def generate_aftercare_item(req: AftercareItemGenerateRequest) -> Dict[str, Any]:
    """为单条预警的指定字段生成话术（非流式）。"""
    try:
        data = AftercareCompanionService().generate_item_field(
            req.customer_id, req.zone, req.rule_id, req.field
        )
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/aftercare/companion/generate/item/stream")
def generate_aftercare_item_stream(req: AftercareItemGenerateRequest) -> StreamingResponse:
    """为单条预警的指定字段流式生成话术。"""
    import json

    svc = AftercareCompanionService()

    def event_stream():
        try:
            for chunk in svc.generate_item_field_stream(
                req.customer_id, req.zone, req.rule_id, req.field
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except ValueError as e:
            payload = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
