"""SOP 产品信息库 API。"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from core.sop_product_library_service import SopProductLibraryService

sop_product_router = APIRouter(prefix="/api/sop", tags=["sop-product-library"])

_svc = SopProductLibraryService()


def _page_payload(rows: list, total: int, page: int, page_size: int) -> Dict[str, Any]:
    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "data": rows,
    }


@sop_product_router.get("/product-library/config")
def sop_product_library_config() -> Dict[str, Any]:
    return {"code": 0, "message": "ok", "data": _svc.get_config()}


@sop_product_router.get("/info-products/")
def sop_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Dict[str, Any]:
    rows, total = _svc.list_products(page=page, page_size=page_size)
    return {"code": 0, "message": "ok", "data": _page_payload(rows, total, page, page_size)}


@sop_product_router.get("/info-products/{product_id}")
def sop_get_product(product_id: str) -> Dict[str, Any]:
    row = _svc.get_product(product_id)
    if not row:
        cfg = _svc.get_config()
        for p in cfg.get("products") or []:
            if p.get("product_id") == product_id:
                return {"code": 0, "message": "ok", "data": p}
        raise HTTPException(status_code=404, detail=f"产品不存在: {product_id}")
    return {"code": 0, "message": "ok", "data": row}


@sop_product_router.post("/info-products/")
def sop_create_product(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = _svc.save_product(body, is_new=True)
        return {"code": 0, "message": "产品创建成功", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@sop_product_router.put("/info-products/{product_id}")
def sop_update_product(product_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(body)
    body["product_id"] = product_id
    try:
        data = _svc.save_product(body, is_new=False)
        return {"code": 0, "message": "产品更新成功", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@sop_product_router.delete("/info-products/{product_id}")
def sop_delete_product(product_id: str) -> Dict[str, Any]:
    try:
        _svc.delete_product(product_id)
        return {"code": 0, "message": "产品删除成功", "data": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@sop_product_router.get("/managers/list")
def sop_list_managers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Dict[str, Any]:
    rows, total = _svc.list_managers(page=page, page_size=page_size)
    enriched = []
    counts: Dict[str, int] = {}
    for p in _svc.get_config().get("products") or []:
        mid = p.get("manager_id") or ""
        counts[mid] = counts.get(mid, 0) + 1
    for m in rows:
        item = dict(m)
        item["product_count"] = counts.get(m.get("id"), 0)
        enriched.append(item)
    return {"code": 0, "message": "ok", "data": _page_payload(enriched, total, page, page_size)}


@sop_product_router.get("/managers/{manager_id}")
def sop_get_manager(manager_id: str) -> Dict[str, Any]:
    mgr = _svc.get_manager_map().get(manager_id)
    cfg = _svc.get_config()
    if not mgr:
        for m in cfg.get("managers") or []:
            if m.get("id") == manager_id:
                mgr = m
                break
    if not mgr:
        raise HTTPException(status_code=404, detail=f"管理人不存在: {manager_id}")
    out = dict(mgr)
    out["product_count"] = sum(
        1 for p in cfg.get("products") or [] if p.get("manager_id") == manager_id
    )
    return {"code": 0, "message": "ok", "data": out}


@sop_product_router.post("/managers/")
def sop_create_manager(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = _svc.save_manager(body, is_new=True)
        return {"code": 0, "message": "管理人创建成功", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@sop_product_router.put("/managers/{manager_id}")
def sop_update_manager(manager_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(body)
    body["id"] = manager_id
    try:
        data = _svc.save_manager(body, is_new=False)
        return {"code": 0, "message": "管理人更新成功", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@sop_product_router.delete("/managers/{manager_id}")
def sop_delete_manager(manager_id: str) -> Dict[str, Any]:
    try:
        _svc.delete_manager(manager_id)
        return {"code": 0, "message": "管理人删除成功", "data": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@sop_product_router.get("/strategies/list")
def sop_list_strategies() -> Dict[str, Any]:
    rows = _svc.list_strategies()
    return {"code": 0, "message": "ok", "data": {"total": len(rows), "data": rows}}


@sop_product_router.post("/strategies/")
def sop_create_strategy(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = _svc.save_strategy(body, is_new=True)
        return {"code": 0, "message": "策略创建成功", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@sop_product_router.put("/strategies/{strategy_id}")
def sop_update_strategy(strategy_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(body)
    body["id"] = strategy_id
    try:
        data = _svc.save_strategy(body, is_new=False)
        return {"code": 0, "message": "策略更新成功", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@sop_product_router.delete("/strategies/{strategy_id}")
def sop_delete_strategy(strategy_id: str) -> Dict[str, Any]:
    try:
        _svc.delete_strategy(strategy_id)
        return {"code": 0, "message": "策略删除成功", "data": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
