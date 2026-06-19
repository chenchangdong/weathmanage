"""统一产品信息库 — 资配底层 + SOP 投后产品。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from core.config_loader import load_sop_product_library
from core.config_writer import save_sop_product_library
from core.product_library_utils import (
    is_allocation_product,
    is_sop_product,
    normalize_product_record,
    sync_risk_fields,
)


def _enabled_products(products: List[dict[str, Any]]) -> List[dict[str, Any]]:
    return [p for p in products if int(p.get("status", 1)) == 1]


def _sop_batch_products(products: List[dict[str, Any]]) -> List[dict[str, Any]]:
    return [p for p in _enabled_products(products) if is_sop_product(p)]


class SopProductLibraryService:
    def get_config(self) -> dict[str, Any]:
        return deepcopy(load_sop_product_library())

    def get_product_map(self) -> dict[str, dict[str, Any]]:
        """SOP 跑批扫描用：仅有管理人的启用产品。"""
        cfg = load_sop_product_library()
        return {
            p["product_id"]: normalize_product_record(dict(p))
            for p in _sop_batch_products(cfg.get("products") or [])
        }

    def get_manager_map(self) -> dict[str, dict[str, Any]]:
        cfg = load_sop_product_library()
        return {m["id"]: dict(m) for m in cfg.get("managers") or [] if int(m.get("status", 1)) == 1}

    def get_product(self, product_id: str) -> Optional[dict[str, Any]]:
        cfg = load_sop_product_library()
        for row in cfg.get("products") or []:
            if row.get("product_id") == product_id:
                return normalize_product_record(dict(row))
        return None

    def list_products(
        self, *, page: int = 1, page_size: int = 20
    ) -> Tuple[List[dict[str, Any]], int]:
        cfg = load_sop_product_library()
        rows = [normalize_product_record(dict(p)) for p in cfg.get("products") or []]
        total = len(rows)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return rows[start:end], total

    def list_managers(
        self, *, page: int = 1, page_size: int = 20
    ) -> Tuple[List[dict[str, Any]], int]:
        cfg = load_sop_product_library()
        rows = list(cfg.get("managers") or [])
        total = len(rows)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return rows[start:end], total

    def list_strategies(self) -> List[dict[str, Any]]:
        return list(load_sop_product_library().get("strategies") or [])

    @staticmethod
    def _build_product_payload(product: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
        base = dict(existing or {})
        base.update({k: v for k, v in product.items() if v is not None})
        pid = (product.get("product_id") or base.get("product_id") or "").strip()
        if not pid:
            raise ValueError("产品代码不能为空")
        base["product_id"] = pid
        base["product_name"] = product.get("product_name") or base.get("product_name") or ""
        pc = (product.get("product_code") or base.get("product_code") or "").strip()
        base["product_code"] = pc or pid

        for key in (
            "manager_id", "manager_name", "category", "asset_type", "strategy_type",
            "rating", "setup_date", "conclusion", "risk", "product_subtype",
        ):
            if key in product:
                base[key] = product.get(key) or ""

        if "asset_type" in product:
            base["asset_type"] = (product.get("asset_type") or "").strip()

        for key in ("init_nav", "score", "rebalance_priority", "min_amount", "max_amount",
                    "liquidity_days", "risk_level", "status"):
            if key in product and product.get(key) not in (None, ""):
                if key in ("init_nav", "score", "min_amount", "max_amount"):
                    base[key] = float(product[key]) if product[key] != "" else base.get(key)
                elif key in ("rebalance_priority", "liquidity_days", "risk_level", "status"):
                    base[key] = int(product[key])
                else:
                    base[key] = product[key]

        base = sync_risk_fields(base)
        return normalize_product_record(base)

    def save_product(self, product: dict[str, Any], *, is_new: bool = False) -> dict[str, Any]:
        cfg = load_sop_product_library()
        products: List[dict[str, Any]] = list(cfg.get("products") or [])
        pid = (product.get("product_id") or "").strip()
        if not pid:
            raise ValueError("产品代码不能为空")
        if is_new and any(p.get("product_id") == pid for p in products):
            raise ValueError(f"产品代码已存在: {pid}")

        existing = next((p for p in products if p.get("product_id") == pid), None)
        payload = self._build_product_payload(product, existing if not is_new else None)

        mgr_id = payload.get("manager_id") or ""
        if mgr_id:
            mgr = self.get_manager_map().get(mgr_id) or {}
            payload["manager_name"] = mgr.get("name") or payload.get("manager_name") or ""

        if is_new:
            products.append(payload)
        else:
            if existing is None:
                raise ValueError(f"产品不存在: {pid}")
            for i, row in enumerate(products):
                if row.get("product_id") == pid:
                    products[i] = payload
                    break
        cfg["products"] = products
        save_sop_product_library(cfg)
        return payload

    def delete_product(self, product_id: str) -> None:
        cfg = load_sop_product_library()
        products = [p for p in cfg.get("products") or [] if p.get("product_id") != product_id]
        if len(products) == len(cfg.get("products") or []):
            raise ValueError(f"产品不存在: {product_id}")
        cfg["products"] = products
        save_sop_product_library(cfg)

    def save_manager(self, manager: dict[str, Any], *, is_new: bool = False) -> dict[str, Any]:
        cfg = load_sop_product_library()
        managers: List[dict[str, Any]] = list(cfg.get("managers") or [])
        mid = (manager.get("id") or "").strip()
        if not mid:
            raise ValueError("管理人ID不能为空")
        if is_new and any(m.get("id") == mid for m in managers):
            raise ValueError(f"管理人ID已存在: {mid}")
        payload = {
            "id": mid,
            "name": manager.get("name") or "",
            "full_name": manager.get("full_name") or "",
            "type": manager.get("type") or "",
            "status": int(manager.get("status", 1)),
            "remark": manager.get("remark") or "",
        }
        if is_new:
            managers.append(payload)
        else:
            found = False
            for i, row in enumerate(managers):
                if row.get("id") == mid:
                    managers[i] = payload
                    found = True
                    break
            if not found:
                raise ValueError(f"管理人不存在: {mid}")
        cfg["managers"] = managers
        self._sync_manager_names_on_products(cfg, payload)
        save_sop_product_library(cfg)
        return payload

    @staticmethod
    def _sync_manager_names_on_products(cfg: dict[str, Any], manager: dict[str, Any]) -> None:
        mid = manager.get("id")
        name = manager.get("name") or ""
        for p in cfg.get("products") or []:
            if p.get("manager_id") == mid:
                p["manager_name"] = name

    def delete_manager(self, manager_id: str) -> None:
        cfg = load_sop_product_library()
        managers = [m for m in cfg.get("managers") or [] if m.get("id") != manager_id]
        if len(managers) == len(cfg.get("managers") or []):
            raise ValueError(f"管理人不存在: {manager_id}")
        cfg["managers"] = managers
        save_sop_product_library(cfg)

    def save_strategy(self, strategy: dict[str, Any], *, is_new: bool = False) -> dict[str, Any]:
        cfg = load_sop_product_library()
        strategies: List[dict[str, Any]] = list(cfg.get("strategies") or [])
        sid = (strategy.get("id") or "").strip()
        if not sid:
            raise ValueError("策略ID不能为空")
        if is_new and any(s.get("id") == sid for s in strategies):
            raise ValueError(f"策略ID已存在: {sid}")
        payload = {
            "id": sid,
            "name": strategy.get("name") or "",
            "manager_id": strategy.get("manager_id") or "",
            "manager_name": strategy.get("manager_name") or "",
            "strategy_type": strategy.get("strategy_type") or "",
            "remark": strategy.get("remark") or "",
            "status": int(strategy.get("status", 1)),
        }
        if is_new:
            strategies.append(payload)
        else:
            found = False
            for i, row in enumerate(strategies):
                if row.get("id") == sid:
                    strategies[i] = payload
                    found = True
                    break
            if not found:
                raise ValueError(f"策略不存在: {sid}")
        cfg["strategies"] = strategies
        save_sop_product_library(cfg)
        return payload

    def delete_strategy(self, strategy_id: str) -> None:
        cfg = load_sop_product_library()
        strategies = [s for s in cfg.get("strategies") or [] if s.get("id") != strategy_id]
        if len(strategies) == len(cfg.get("strategies") or []):
            raise ValueError(f"策略不存在: {strategy_id}")
        cfg["strategies"] = strategies
        save_sop_product_library(cfg)
