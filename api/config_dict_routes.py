"""可视化数据字典 API。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from core.config_dict_service import get_tree, load_module, save_module

config_dict_router = APIRouter(prefix="/api/config-dict", tags=["config-dict"])


@config_dict_router.get("/tree")
def config_dict_tree() -> Dict[str, Any]:
    """左侧分类树。"""
    return {"code": 0, "message": "ok", "data": get_tree()}


@config_dict_router.get("/module/{module_id}")
def config_dict_get_module(module_id: str) -> Dict[str, Any]:
    """读取单个配置模块。"""
    try:
        return {"code": 0, "message": "ok", "data": load_module(module_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@config_dict_router.put("/module/{module_id}")
def config_dict_save_module(module_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """保存单个配置模块。"""
    try:
        data = save_module(module_id, body)
        return {"code": 0, "message": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
