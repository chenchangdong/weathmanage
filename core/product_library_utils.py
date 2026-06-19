"""统一产品库 — 字段规范化与资配/SOP 产品判定。"""

from __future__ import annotations

from typing import Any

RISK_LEVEL_TO_CATEGORY: dict[int, str] = {1: "low", 2: "low", 3: "mod", 4: "agg", 5: "agg"}
CATEGORY_TO_RISK_LEVEL: dict[str, int] = {"low": 1, "mod": 3, "agg": 4}


def is_allocatable_product(product: dict[str, Any]) -> bool:
    """纳入资配候选/调仓 map：已配置 asset_type 的产品（含资配底层与 SOP）。"""
    return bool((product.get("asset_type") or "").strip())


def is_allocation_product(product: dict[str, Any]) -> bool:
    """资配底层产品：含 rebalance_priority（含 0）。"""
    return "rebalance_priority" in product


def is_sop_product(product: dict[str, Any]) -> bool:
    """SOP 投后产品：含管理人。"""
    return bool((product.get("manager_id") or "").strip())


def allocation_product_id(raw_id: str) -> str:
    """资配编码 P000 → 000；纯数字规范为三位字符串。"""
    pid = str(raw_id or "").strip()
    if len(pid) == 4 and pid.startswith("P") and pid[1:].isdigit():
        pid = pid[1:]
    if pid.isdigit():
        return pid.zfill(3)
    return pid


def normalize_product_record(product: dict[str, Any]) -> dict[str, Any]:
    """合并 product_id/product_name 与 code/name，补全 product_code。"""
    p = dict(product)
    raw_id = p.get("product_id") or p.get("code") or ""
    if is_allocation_product(p):
        pid = allocation_product_id(str(raw_id))
    else:
        pid = str(raw_id).strip()
    name = (p.get("product_name") or p.get("name") or "").strip()

    p["product_id"] = pid
    p["code"] = pid
    p["product_name"] = name
    p["name"] = name
    if not (p.get("product_code") or "").strip():
        p["product_code"] = pid

    if is_allocation_product(p):
        rl = p.get("risk_level")
        if rl is not None and not (p.get("category") or "").strip():
            try:
                p["category"] = RISK_LEVEL_TO_CATEGORY.get(int(rl), "")
            except (TypeError, ValueError):
                pass
        elif (p.get("category") or "").strip() and rl is None:
            p["risk_level"] = CATEGORY_TO_RISK_LEVEL.get(str(p["category"]), 1)

    return p


def sync_risk_fields(product: dict[str, Any]) -> dict[str, Any]:
    """保存时同步 risk_level 与 category（low/mod/agg）。"""
    p = dict(product)
    cat = (p.get("category") or "").strip()
    rl = p.get("risk_level")
    if rl is not None and str(rl) != "":
        try:
            p["category"] = RISK_LEVEL_TO_CATEGORY.get(int(rl), cat)
        except (TypeError, ValueError):
            pass
    elif cat:
        p["risk_level"] = CATEGORY_TO_RISK_LEVEL.get(cat, p.get("risk_level"))
    return p
