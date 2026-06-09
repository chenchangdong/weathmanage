"""Data models for asset allocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HoldingItem:
    product_code: str
    amount: float


@dataclass
class CategorySnapshot:
    category: str
    category_name: str
    current_amount: float
    current_ratio: float
    target_amount: float
    target_ratio: float
    deviation: float
    deviation_pct: str
    band: list[float]
    in_band: bool
    health_level: str
    products: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProductDelta:
    product_code: str
    product_name: str
    category: str
    current_amount: float
    target_amount: float
    delta_amount: float
    action: str  # buy / sell / hold
    limit_hit: bool = False
    limit_side: str = ""  # max / liquidate


@dataclass
class RebalanceResult:
    customer_id: str
    risk_profile: str
    total_assets: float
    idle_cash: float
    category_targets: dict[str, float]
    category_summary: list[dict[str, Any]]
    product_deltas: list[ProductDelta]
    validation_notes: list[str]
    mode: str = "smart_one_click"
    locked_categories: list[str] = field(default_factory=list)
    view_mode: str = "four_money"
    product_category: str = "投资规划"


@dataclass
class AssetOverview:
    customer_id: str
    customer_name: str
    risk_profile: str
    risk_profile_name: str
    total_assets: float
    idle_cash: float
    health_level: str
    health_label: str
    health_color: str
    categories: list[CategorySnapshot]
    page_config: dict[str, Any]
    permissions: dict[str, bool]
    product_category: str = "投资规划"
    view_mode: str = "four_money"
    allocation_mapping: Any = None
    excluded_insurance_amount: float = 0.0
