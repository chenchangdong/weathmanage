"""YAML 配置持久化 — 临时替代 DB，后续可替换为数据库读写。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.config_loader import CONFIG_DIR, reload_all_configs

# DB 读写占位（保留注释备用）
# def save_model_to_db(data): ...
# def load_model_from_db(): ...


def _dump_yaml(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )


def apply_model_code_renames(renames: List[Dict[str, str]]) -> None:
    """模型编码变更时，同步更新 portfolio_mapping 中的 target_model 引用。"""
    if not renames:
        return
    path = CONFIG_DIR / "portfolio_mapping.yaml"
    with open(path, encoding="utf-8") as f:
        mapping = yaml.safe_load(f) or {}
    portfolio_map = mapping.get("portfolio_map") or {}
    for item in renames:
        old_code = (item.get("from") or item.get("from_code") or "").strip()
        new_code = (item.get("to") or item.get("to_code") or "").strip()
        if not old_code or not new_code or old_code == new_code:
            continue
        for _cat, loss_map in portfolio_map.items():
            if not isinstance(loss_map, dict):
                continue
            for _loss_key, entry in loss_map.items():
                if isinstance(entry, dict) and entry.get("target_model") == old_code:
                    entry["target_model"] = new_code
    mapping["portfolio_map"] = portfolio_map
    _dump_yaml(path, mapping)


def delete_model(model_code: str) -> None:
    """从 model_config.yaml 删除模型（调用前须确认无风险映射引用）。"""
    path = CONFIG_DIR / "model_config.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    model_list = data.get("model_list") or {}
    if model_code not in model_list:
        raise ValueError(f"模型不存在: {model_code}")
    if len(model_list) <= 1:
        raise ValueError("至少保留一个资产配置模型，无法删除")
    del model_list[model_code]
    data["model_list"] = model_list
    _dump_yaml(path, data)
    reload_all_configs()


def save_model_config(
    model_list: Dict[str, Any],
    version: str = "1.0",
    code_renames: Optional[List[Dict[str, str]]] = None,
) -> None:
    """页面A保存 → model_config.yaml"""
    if code_renames:
        apply_model_code_renames(code_renames)
    payload = {"version": version, "model_list": model_list}
    _dump_yaml(CONFIG_DIR / "model_config.yaml", payload)
    reload_all_configs()


def _strip_portfolio_map_metrics(portfolio_map: Dict[str, Any]) -> Dict[str, Any]:
    """收益/波动仅来自 model_config，映射表不持久化 ret/vol。"""
    cleaned: Dict[str, Any] = {}
    for cat, loss_map in (portfolio_map or {}).items():
        if not isinstance(loss_map, dict):
            cleaned[cat] = loss_map
            continue
        cleaned[cat] = {}
        for loss_key, entry in loss_map.items():
            if not isinstance(entry, dict):
                cleaned[cat][loss_key] = entry
                continue
            item = dict(entry)
            item.pop("ret", None)
            item.pop("vol", None)
            cleaned[cat][loss_key] = item
    return cleaned


def save_portfolio_mapping(
    portfolio_map: Dict[str, Any],
    risk_customer_map: Optional[Dict[str, str]] = None,
    risk_loss_default: Optional[Dict[str, Any]] = None,
    customer_risk_levels: Optional[List[Any]] = None,
    version: str = "1.1",
) -> None:
    """页面B保存 → portfolio_mapping.yaml"""
    existing = {}
    path = CONFIG_DIR / "portfolio_mapping.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}

    payload: Dict[str, Any] = {
        "version": version,
        "customer_risk_levels": customer_risk_levels or existing.get("customer_risk_levels", []),
        "risk_loss_default": risk_loss_default or existing.get("risk_loss_default", {}),
        "portfolio_map": _strip_portfolio_map_metrics(portfolio_map),
        "risk_customer_map": risk_customer_map or existing.get("risk_customer_map", {}),
    }
    _dump_yaml(path, payload)
    reload_all_configs()


def save_sop_product_library(config: Dict[str, Any], version: str = "1.0") -> None:
    """SOP 产品信息库 → sop_product_library.yaml（独立于资配 product_constraint）"""
    payload = dict(config)
    payload["version"] = version
    _dump_yaml(CONFIG_DIR / "sop_product_library.yaml", payload)
    reload_all_configs()


def save_sop_rule_system(config: Dict[str, Any], version: str = "1.0") -> None:
    """SOP 规则策略配置 → sop_rule_system.yaml"""
    payload = dict(config)
    payload["version"] = version
    _dump_yaml(CONFIG_DIR / "sop_rule_system.yaml", payload)
    reload_all_configs()
