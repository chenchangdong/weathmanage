"""可视化数据字典 — 可编辑 config 模块注册表（不含 customer_profile / 已有专属页面的配置）。"""

from __future__ import annotations

from typing import Any, Dict, List

# 左侧树：group 节点含 children；leaf 节点含 module_id
CONFIG_DICT_TREE: List[Dict[str, Any]] = [
    {
        "id": "grp_four_money",
        "code": "four_money",
        "name": "四笔钱与映射",
        "type": "group",
        "children": [
            {"id": "four_money_categories", "code": "four_money_categories", "name": "四笔钱大类", "type": "module"},
            {"id": "asset_type_alias", "code": "asset_type_alias", "name": "资产类型别名", "type": "module"},
            {"id": "category_code_map", "code": "category_code_map", "name": "大类编码映射", "type": "module"},
            {"id": "four_money_asset_bind", "code": "four_money_asset_bind", "name": "资产类型绑定", "type": "module"},
        ],
    },
    {
        "id": "grp_solver",
        "code": "solver",
        "name": "求解与约束",
        "type": "group",
        "children": [
            {"id": "solver_params", "code": "solver_params", "name": "求解器参数", "type": "module"},
            {"id": "page_constraint", "code": "page_constraint", "name": "操作与权限约束", "type": "module"},
        ],
    },
    {
        "id": "grp_display",
        "code": "display",
        "name": "展示与视图",
        "type": "group",
        "children": [
            {"id": "allocation_view_profiles", "code": "allocation_view_profiles", "name": "规划视图配置", "type": "module"},
            {"id": "page_header_health", "code": "page_header_health", "name": "页面标题与健康度", "type": "module"},
            {"id": "category_card_labels", "code": "category_card_labels", "name": "卡片文案", "type": "module"},
        ],
    },
    {
        "id": "grp_llm",
        "code": "llm",
        "name": "智能服务",
        "type": "group",
        "children": [
            {"id": "llm_config", "code": "llm_config", "name": "大模型参数", "type": "module"},
        ],
    },
]

# 模块元数据：view_type = table | form
MODULE_META: Dict[str, Dict[str, Any]] = {
    "four_money_categories": {
        "view_type": "table",
        "file": "four_money_rule.yaml",
        "desc": "四笔钱大类定义（名称、图标、描述、优先级）",
        "id_key": "code",
        "columns": [
            {"key": "code", "label": "编码", "type": "text", "required": True, "readonly_on_edit": True},
            {"key": "name", "label": "名称", "type": "text", "required": True},
            {"key": "icon", "label": "图标", "type": "text"},
            {"key": "description", "label": "描述", "type": "textarea"},
            {"key": "priority", "label": "优先级", "type": "number"},
        ],
    },
    "asset_type_alias": {
        "view_type": "table",
        "file": "four_money_mapping.yaml",
        "desc": "五类资产类型的中文别名",
        "id_key": "code",
        "columns": [
            {"key": "code", "label": "类型编码", "type": "text", "required": True, "readonly_on_edit": True},
            {"key": "name", "label": "显示名称", "type": "text", "required": True},
        ],
    },
    "category_code_map": {
        "view_type": "table",
        "file": "four_money_mapping.yaml",
        "desc": "四笔钱 YAML 键 → 引擎 category code",
        "id_key": "four_money_key",
        "columns": [
            {"key": "four_money_key", "label": "四笔钱键", "type": "text", "required": True, "readonly_on_edit": True},
            {"key": "engine_code", "label": "引擎编码", "type": "text", "required": True},
        ],
    },
    "four_money_asset_bind": {
        "view_type": "table",
        "file": "four_money_mapping.yaml",
        "desc": "四笔钱大类绑定的底层 asset_type 列表",
        "id_key": "key",
        "columns": [
            {"key": "key", "label": "四笔钱键", "type": "text", "required": True, "readonly_on_edit": True},
            {"key": "asset_types", "label": "资产类型（逗号分隔）", "type": "text", "required": True},
            {"key": "threshold_aggregate", "label": "阈值合并规则", "type": "text"},
        ],
    },
    "solver_params": {
        "view_type": "form",
        "file": "four_money_rule.yaml",
        "desc": "AutoRebalanceEngine 一键/单类配仓求解行为，对应 four_money_rule.yaml → solver 节点",
        "sections": [
            {
                "title": "求解器参数",
                "prefix": "solver",
                "fields": [
                    {
                        "key": "prefer_existing_holdings",
                        "label": "优先按持仓占比分摊",
                        "type": "boolean",
                        "default": True,
                        "hint": "consolidate=false 时生效：大类目标按各产品当前持仓占比分摊",
                    },
                    {
                        "key": "minimize_cash_movement",
                        "label": "最小资金异动",
                        "type": "boolean",
                        "default": True,
                        "hint": "大类已在模型区间内时保持现仓，越界时再向区间内靠拢",
                    },
                    {
                        "key": "consolidate_category_rebalance",
                        "label": "类内集中调仓",
                        "type": "boolean",
                        "default": True,
                        "hint": "优先于持仓占比分摊：仅最高优先级产品承接大类增减",
                    },
                    {
                        "key": "liquidate_below_min",
                        "label": "低于下限可清仓",
                        "type": "boolean",
                        "default": True,
                        "hint": "理想目标低于 min_amount 时是否允许清仓为 0",
                    },
                    {
                        "key": "max_iterations",
                        "label": "最大迭代轮数",
                        "type": "number",
                        "default": 10,
                        "hint": "产品触顶冻结后重算其余大类的最大轮数",
                    },
                    {
                        "key": "convergence_threshold",
                        "label": "收敛阈值",
                        "type": "number",
                        "default": 0.001,
                        "hint": "预留参数，当前引擎未使用",
                    },
                    {
                        "key": "fallback_strategy",
                        "label": "越界回退策略",
                        "type": "select",
                        "default": "benchmark",
                        "options": ["benchmark", "band_midpoint", "band_low", "band_high"],
                        "hint": "minimize_cash_movement=true 且大类越界时的目标落点",
                    },
                ],
            }
        ],
    },
    "page_constraint": {
        "view_type": "form",
        "file": "page_constraint.yaml",
        "desc": "前端按钮权限、微调规则与优化约束",
        "sections": [
            {
                "title": "操作模式",
                "fields": [
                    {"key": "modes.default", "label": "默认模式", "type": "text"},
                    {"key": "modes.available", "label": "可用模式（逗号分隔）", "type": "text", "list": True},
                ],
            },
            {
                "title": "理财经理权限",
                "prefix": "permissions.advisor",
                "fields": [
                    {"key": "can_full_optimize", "label": "全账户优化", "type": "boolean"},
                    {"key": "can_single_optimize", "label": "单类优化", "type": "boolean"},
                    {"key": "can_manual_tweak", "label": "人工微调", "type": "boolean"},
                    {"key": "can_generate_explanation", "label": "生成解读", "type": "boolean"},
                ],
            },
            {
                "title": "只读用户权限",
                "prefix": "permissions.viewer",
                "fields": [
                    {"key": "can_full_optimize", "label": "全账户优化", "type": "boolean"},
                    {"key": "can_single_optimize", "label": "单类优化", "type": "boolean"},
                    {"key": "can_manual_tweak", "label": "人工微调", "type": "boolean"},
                    {"key": "can_generate_explanation", "label": "生成解读", "type": "boolean"},
                ],
            },
            {
                "title": "人工微调",
                "prefix": "manual_tweak",
                "fields": [
                    {"key": "enabled", "label": "启用", "type": "boolean"},
                    {"key": "dialog_title", "label": "弹窗标题", "type": "text"},
                    {"key": "realtime_recalc", "label": "实时重算", "type": "boolean"},
                    {"key": "locked_categories", "label": "锁定大类（逗号分隔）", "type": "text", "list": True},
                ],
            },
            {
                "title": "单类 / 全账户优化",
                "fields": [
                    {
                        "key": "single_category_optimize.allowed_categories",
                        "label": "允许单类优化的大类",
                        "type": "text",
                        "list": True,
                    },
                    {"key": "single_category_optimize.freeze_other_categories", "label": "冻结其他大类", "type": "boolean"},
                    {"key": "full_account_optimize.include_idle_cash", "label": "纳入追加持仓", "type": "boolean"},
                    {"key": "full_account_optimize.min_total_assets", "label": "最低可优化资产", "type": "number"},
                    {"key": "full_account_optimize.max_single_product_ratio", "label": "单产品占比上限", "type": "number"},
                ],
            },
            {
                "title": "校验与结果页",
                "fields": [
                    {"key": "product_limit_validation.enabled", "label": "产品上下限校验", "type": "boolean"},
                    {"key": "result_page.require_in_band", "label": "强制落在区间", "type": "boolean"},
                    {"key": "result_page.show_validation_warnings", "label": "显示校验警告", "type": "boolean"},
                    {"key": "result_page.allow_export_pdf", "label": "允许导出 PDF", "type": "boolean"},
                ],
            },
        ],
    },
    "allocation_view_profiles": {
        "view_type": "table",
        "file": "allocation_view.yaml",
        "desc": "规划类型对应的前台卡片视图",
        "id_key": "profile_name",
        "columns": [
            {"key": "profile_name", "label": "规划类型", "type": "text", "required": True, "readonly_on_edit": True},
            {"key": "view_mode", "label": "视图模式", "type": "select", "options": ["four_money", "asset_type"]},
            {"key": "card_keys", "label": "卡片键（逗号分隔）", "type": "text", "required": True},
            {"key": "excluded_asset_types", "label": "排除资产类型", "type": "text"},
        ],
    },
    "page_header_health": {
        "view_type": "form",
        "file": "four_money_page.yaml",
        "desc": "客户资产页标题与健康度配色",
        "sections": [
            {
                "title": "页面",
                "fields": [
                    {"key": "page.title", "label": "页面标题", "type": "text"},
                    {"key": "page.subtitle", "label": "副标题", "type": "text"},
                ],
            },
            {
                "title": "顶部卡片",
                "prefix": "header_card",
                "fields": [
                    {"key": "show_total_assets", "label": "显示总资产", "type": "boolean"},
                    {"key": "show_idle_cash", "label": "显示追加持仓", "type": "boolean"},
                    {"key": "show_health_badge", "label": "显示健康度", "type": "boolean"},
                    {"key": "idle_cash_label", "label": "追加持仓文案", "type": "text"},
                    {"key": "total_assets_label", "label": "总资产文案", "type": "text"},
                ],
            },
            {
                "title": "健康度",
                "fields": [
                    {"key": "health_thresholds.green.label", "label": "健康标签", "type": "text"},
                    {"key": "health_thresholds.green.color", "label": "健康颜色", "type": "text"},
                    {"key": "health_thresholds.red.label", "label": "需优化标签", "type": "text"},
                    {"key": "health_thresholds.red.color", "label": "需优化颜色", "type": "text"},
                ],
            },
        ],
    },
    "category_card_labels": {
        "view_type": "table",
        "file": "four_money_page.yaml",
        "desc": "四笔钱卡片标题与副标题",
        "id_key": "category",
        "columns": [
            {"key": "category", "label": "大类编码", "type": "text", "required": True, "readonly_on_edit": True},
            {"key": "title", "label": "卡片标题", "type": "text", "required": True},
            {"key": "subtitle", "label": "副标题", "type": "text"},
        ],
    },
    "llm_config": {
        "view_type": "form",
        "file": "llm_config.yaml",
        "desc": "大模型连接参数（API Key 仍从环境变量读取）",
        "sections": [
            {
                "title": "连接",
                "fields": [
                    {"key": "provider", "label": "Provider", "type": "text"},
                    {"key": "base_url", "label": "Base URL", "type": "text"},
                    {"key": "model", "label": "模型", "type": "text"},
                    {"key": "api_key_env", "label": "API Key 环境变量", "type": "text", "readonly": True},
                    {"key": "api_key_fallback_env", "label": "备用 Key 环境变量", "type": "text", "readonly": True},
                ],
            },
            {
                "title": "生成参数",
                "fields": [
                    {"key": "temperature", "label": "Temperature", "type": "number"},
                    {"key": "max_tokens", "label": "Max Tokens", "type": "number"},
                    {"key": "timeout_seconds", "label": "超时(秒)", "type": "number"},
                    {"key": "enable_thinking", "label": "开启思考链", "type": "boolean"},
                    {"key": "thinking_budget", "label": "思考 Token 预算", "type": "number"},
                ],
            },
            {
                "title": "顾问对话",
                "prefix": "chat",
                "fields": [
                    {"key": "max_history_turns", "label": "最大历史轮数", "type": "number"},
                    {"key": "max_reply_tokens", "label": "最大回复 Tokens", "type": "number"},
                    {"key": "thinking_budget", "label": "思考预算", "type": "number"},
                    {"key": "disclaimer", "label": "免责声明", "type": "textarea"},
                ],
            },
            {
                "title": "场景开关",
                "prefix": "scenes.advisor_chat",
                "fields": [
                    {"key": "enabled", "label": "顾问对话启用", "type": "boolean"},
                ],
            },
        ],
    },
}
