"""Configuration loader — all business rules from YAML."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_four_money_rule() -> dict[str, Any]:
    return _load_yaml("four_money_rule.yaml")


@lru_cache(maxsize=1)
def load_product_library() -> dict[str, Any]:
    return _load_yaml("product_library.yaml")


@lru_cache(maxsize=1)
def load_product_constraint() -> dict[str, Any]:
    """兼容：返回资配产品子集视图（原 product_constraint 结构）。"""
    lib = load_product_library()
    from core.product_library_utils import is_allocatable_product, normalize_product_record

    products = [
        normalize_product_record(p)
        for p in lib.get("products") or []
        if is_allocatable_product(p)
    ]
    return {
        "version": lib.get("version", "2.0"),
        "asset_types": lib.get("asset_types") or {},
        "products": products,
    }


@lru_cache(maxsize=1)
def load_sop_product_library() -> dict[str, Any]:
    """兼容：SOP 模块读取统一产品库。"""
    return load_product_library()


@lru_cache(maxsize=1)
def load_customer_profile() -> dict[str, Any]:
    return _load_yaml("customer_profile.yaml")


@lru_cache(maxsize=1)
def load_four_money_page() -> dict[str, Any]:
    return _load_yaml("four_money_page.yaml")


@lru_cache(maxsize=1)
def load_page_constraint() -> dict[str, Any]:
    return _load_yaml("page_constraint.yaml")


def is_product_limit_validation_enabled() -> bool:
    """是否启用产品 min_amount / max_amount 校验（默认 false）。"""
    cfg = load_page_constraint().get("product_limit_validation", {})
    return bool(cfg.get("enabled", False))


@lru_cache(maxsize=1)
def load_sop_rule_system() -> dict[str, Any]:
    return _load_yaml("sop_rule_system.yaml")


@lru_cache(maxsize=1)
def load_sop_agent_system() -> dict[str, Any]:
    return _load_yaml("sop_agent_system.yaml")


@lru_cache(maxsize=1)
def load_sop_research_frameworks() -> dict[str, Any]:
    return _load_yaml("sop_research_frameworks.yaml")


@lru_cache(maxsize=1)
def load_sop_script_templates() -> dict[str, Any]:
    return _load_yaml("sop_script_templates.yaml")


@lru_cache(maxsize=1)
def load_sop_banned_words() -> dict[str, Any]:
    return _load_yaml("sop_banned_words.yaml")


@lru_cache(maxsize=1)
def load_advisor_directory() -> dict[str, Any]:
    return _load_yaml("advisor_directory.yaml")


def get_advisor_map() -> dict[str, dict[str, Any]]:
    cfg = load_advisor_directory()
    return {a["id"]: dict(a) for a in cfg.get("advisors") or [] if a.get("id")}


def get_default_advisor_id() -> str:
    profile = load_customer_profile()
    if profile.get("default_advisor_id"):
        return str(profile["default_advisor_id"])
    return str(load_advisor_directory().get("default_advisor_id") or "")


def get_feishu_app_credentials() -> tuple[str, str]:
    """飞书应用凭证：优先读环境变量，勿写入配置文件。"""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    return app_id, app_secret


@lru_cache(maxsize=1)
def load_four_money_mapping() -> dict[str, Any]:
    return _load_yaml("four_money_mapping.yaml")


@lru_cache(maxsize=1)
def load_model_config() -> dict[str, Any]:
    return _load_yaml("model_config.yaml")


@lru_cache(maxsize=1)
def load_portfolio_mapping() -> dict[str, Any]:
    return _load_yaml("portfolio_mapping.yaml")


@lru_cache(maxsize=1)
def load_llm_config() -> dict[str, Any]:
    return _load_yaml("llm_config.yaml")


@lru_cache(maxsize=1)
def load_allocation_view() -> dict[str, Any]:
    return _load_yaml("allocation_view.yaml")


INVESTMENT_CARD_KEYS = ("cash", "fixed_income", "equity", "alternative")


def get_view_profile(product_category: str) -> dict[str, Any]:
    profiles = load_allocation_view().get("view_profiles", {})
    return profiles.get(
        product_category,
        {"view_mode": "four_money", "card_keys": list(get_category_names().keys())},
    )


def get_allocation_view_mode(product_category: str) -> str:
    return get_view_profile(product_category).get("view_mode", "four_money")


def get_display_category_names(view_mode: str) -> dict[str, str]:
    if view_mode == "asset_type":
        return get_asset_type_aliases()
    return get_category_names()


def reload_all_configs() -> None:
    """Clear cache after config hot-reload."""
    load_four_money_rule.cache_clear()
    load_product_library.cache_clear()
    load_product_constraint.cache_clear()
    load_customer_profile.cache_clear()
    load_four_money_page.cache_clear()
    load_page_constraint.cache_clear()
    load_sop_product_library.cache_clear()
    load_sop_rule_system.cache_clear()
    load_sop_agent_system.cache_clear()
    load_sop_research_frameworks.cache_clear()
    load_sop_script_templates.cache_clear()
    load_sop_banned_words.cache_clear()
    load_advisor_directory.cache_clear()
    load_four_money_mapping.cache_clear()
    load_model_config.cache_clear()
    load_portfolio_mapping.cache_clear()
    load_llm_config.cache_clear()
    load_allocation_view.cache_clear()
    get_asset_type_to_category.cache_clear()


@lru_cache(maxsize=1)
def get_asset_type_to_category() -> dict[str, str]:
    """产品类型 asset_type → 四笔钱引擎 category（spend/preserve/grow/protect）。"""
    fm = load_four_money_mapping()
    code_map = fm.get("category_code_map", {})
    result: dict[str, str] = {}
    for fm_key, rule in fm.get("four_money_rule", {}).items():
        engine_cat = code_map.get(fm_key, fm_key)
        for asset_type in rule.get("asset_type", []):
            result[asset_type] = engine_cat
    return result


def get_asset_type_aliases() -> dict[str, str]:
    return load_four_money_mapping().get("asset_alias", {})


def enrich_product(product: dict[str, Any]) -> dict[str, Any]:
    """
    为产品补充派生字段：
    - four_money_category: 四笔钱大类（由 asset_type 经 four_money_mapping 推导）
    - asset_type_name: 资产类型中文名
    - code/name: 与 product_id/product_name 对齐
    """
    from core.product_library_utils import normalize_product_record, is_allocatable_product

    p = normalize_product_record(product)
    asset_type = p.get("asset_type")
    aliases = get_asset_type_aliases()
    if asset_type:
        p["asset_type_name"] = aliases.get(asset_type, asset_type)
        mapping = get_asset_type_to_category()
        if asset_type in mapping:
            p["four_money_category"] = mapping[asset_type]
    return p


def get_all_products() -> list[dict[str, Any]]:
    from core.product_library_utils import is_allocatable_product

    products = load_product_library().get("products", [])
    rows = [p for p in products if is_allocatable_product(p)]
    return [enrich_product(p) for p in rows]


def get_all_library_products() -> list[dict[str, Any]]:
    """统一产品库全部条目（资配 + SOP）。"""
    from core.product_library_utils import normalize_product_record

    return [normalize_product_record(p) for p in load_product_library().get("products") or []]


def get_products_by_category() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for p in get_all_products():
        cat = p.get("four_money_category")
        if not cat:
            continue
        result.setdefault(cat, []).append(p)
    return result


def get_products_by_asset_type() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for p in get_all_products():
        at = p.get("asset_type", "unknown")
        result.setdefault(at, []).append(p)
    return result


def get_products_for_display_category(category: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    按前台卡片 category 查询候选产品。
    - 四笔钱：spend / preserve / grow / protect
    - 资产类型：cash / fixed_income / equity / alternative / insurance
    """
    by_four = get_products_by_category()
    if category in by_four:
        return by_four[category], get_category_names()
    by_asset = get_products_by_asset_type()
    if category in by_asset:
        return by_asset[category], get_asset_type_aliases()
    return [], {}


def get_product_map() -> dict[str, dict[str, Any]]:
    return {p["product_id"]: p for p in get_all_products()}


def get_demo_customer(customer_id: str) -> dict[str, Any] | None:
    for c in load_customer_profile().get("demo_customers", []):
        if c["customer_id"] == customer_id:
            return c
    return None


def get_category_names() -> dict[str, str]:
    rule = load_four_money_rule()
    return {code: info["name"] for code, info in rule.get("categories", {}).items()}


def get_customer_risk_levels() -> list[dict[str, Any]]:
    """五档客户风险等级（与投资组合偏好一一对应）。"""
    mapping = load_portfolio_mapping()
    levels = mapping.get("customer_risk_levels")
    if levels:
        return levels
    profile = load_customer_profile()
    risk_map = mapping.get("risk_customer_map", {})
    return [
        {"code": code, "name": name.split("(")[0], "loss_key": None}
        for code, name in risk_map.items()
    ]


def get_risk_level_name(risk_code: str) -> str:
    profile = load_customer_profile()
    levels = profile.get("risk_levels", {})
    if risk_code in levels:
        return levels[risk_code].get("name", risk_code)
    mapping = load_portfolio_mapping()
    return mapping.get("risk_customer_map", {}).get(risk_code, risk_code)
