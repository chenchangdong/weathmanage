"""API request/response schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AutoRebalanceRequest(BaseModel):
    customer_id: str
    mode: str = "smart_one_click"
    target_category: Optional[str] = None
    product_category: Optional[str] = None
    locked_categories: List[str] = Field(default_factory=list)
    manual_overrides: Dict[str, float] = Field(default_factory=dict)
    holdings: Optional[Dict[str, float]] = None
    idle_cash: Optional[float] = None
    loss_key: Optional[str] = None


class ManualAdjustRequest(BaseModel):
    customer_id: str
    product_targets: Dict[str, float]
    baseline_product_targets: Optional[Dict[str, float]] = None
    product_category: Optional[str] = None
    holdings: Optional[Dict[str, float]] = None
    idle_cash: Optional[float] = None
    loss_key: Optional[str] = None


class FlagCategorySuggestRequest(BaseModel):
    customer_id: str
    category: str
    category_targets: Dict[str, float]
    baseline_product_targets: Optional[Dict[str, float]] = None
    product_category: Optional[str] = None
    holdings: Optional[Dict[str, float]] = None
    idle_cash: Optional[float] = None
    loss_key: Optional[str] = None


class ModelCodeRename(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_code: str = Field(..., alias="from")
    to_code: str = Field(..., alias="to")


class ModelSaveRequest(BaseModel):
    model_list: Dict[str, Any]
    code_renames: List[ModelCodeRename] = Field(default_factory=list)


class ModelDeleteRequest(BaseModel):
    model_code: str


class PortfolioMapSaveRequest(BaseModel):
    portfolio_map: Dict[str, Any]
    risk_customer_map: Optional[Dict[str, str]] = None
    risk_loss_default: Optional[Dict[str, Any]] = None
    customer_risk_levels: Optional[List[Dict[str, Any]]] = None


class AftercareCompanionRequest(BaseModel):
    customer_id: str


class AftercareItemGenerateRequest(BaseModel):
    customer_id: str
    zone: str = Field(..., description="research | product")
    rule_id: str
    field: str = Field(..., description="advisor_strategy | customer_script")


class AftercareSystemSaveRequest(BaseModel):
    config: Dict[str, Any]
    version: str = "1.0"


class ExplainRequest(BaseModel):
    customer_id: str
    rebalance_result: Optional[Dict[str, Any]] = None


class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str


class AdvisorChatRequest(BaseModel):
    customer_id: str
    message: str
    history: List[ChatMessage] = Field(default_factory=list)
    overview: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    diagnosis: Optional[Dict[str, Any]] = None
