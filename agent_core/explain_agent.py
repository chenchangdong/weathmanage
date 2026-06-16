"""Explain agent — generates allocation explanation and client communication scripts."""

from __future__ import annotations

from typing import Any

from core.config_loader import (
    get_category_names,
    get_demo_customer,
    get_display_category_names,
    get_risk_level_name,
    load_four_money_rule,
)
from core.models import RebalanceResult


class ExplainAgent:
    """接收调仓结果，生成理财经理配置说明 + 客户沟通话术。"""

    @staticmethod
    def _addon_holding_clause(idle_cash: float) -> str:
        if idle_cash and idle_cash > 0.01:
            return f"（含追加持仓{idle_cash:,.0f}元）"
        return ""

    def generate(self, result: RebalanceResult) -> dict[str, Any]:
        customer = get_demo_customer(result.customer_id)
        if not customer:
            raise ValueError(f"Customer not found: {result.customer_id}")

        names = get_display_category_names(result.view_mode)
        risk_name = get_risk_level_name(result.risk_profile)

        allocation_logic = self._build_allocation_logic(result, names, risk_name)
        over_under_reason = self._build_over_under_reason(result, names)
        customer_fit = self._build_customer_fit(customer, result, risk_name)
        manager_summary = self._build_manager_summary(result, customer, names, risk_name)
        client_script = self._build_client_script(result, customer, names, risk_name)

        return {
            "customer_id": result.customer_id,
            "allocation_logic": allocation_logic,
            "over_under_reason": over_under_reason,
            "customer_fit": customer_fit,
            "manager_summary": manager_summary,
            "client_script": client_script,
        }

    def _build_allocation_logic(
        self, result: RebalanceResult, names: dict[str, str], risk_name: str
    ) -> str:
        if result.mode == "manual_product_edit":
            lines = [
                f"基于客户{risk_name}风险画像，总资产{result.total_assets:,.0f}元{self._addon_holding_clause(result.idle_cash)}，",
                "理财经理已对智能方案进行人工二次调整，当前为产品级目标配置：",
            ]
        elif result.mode == "flag_personalized":
            scope_note = (
                "（保障类持仓不计入投资规划可配置总资产）"
                if result.view_mode == "asset_type"
                else ""
            )
            lines = [
                f"基于客户{risk_name}风险画像，"
                f"可配置总资产{result.total_assets:,.0f}元{scope_note}"
                f"{self._addon_holding_clause(result.idle_cash)}，",
                "根据财富健康标志诊断结果，采用「个性化智能配仓」策略，生成资产类型配置方案：",
            ]
        elif result.mode == "optimal_personalized":
            scope_note = (
                "（保障类持仓不计入投资规划可配置总资产）"
                if result.view_mode == "asset_type"
                else ""
            )
            strategy = self._describe_solver_strategy()
            lines = [
                f"基于客户{risk_name}风险画像，"
                f"可配置总资产{result.total_assets:,.0f}元{scope_note}"
                f"{self._addon_holding_clause(result.idle_cash)}，",
                f"采用「{strategy}」策略下的「个性化智能配仓（新）」，"
                "生成资产类型大类处方（产品层待落实）：",
            ]
        else:
            strategy = self._describe_solver_strategy()
            plan_label = (
                "资产类型最优配置方案"
                if result.view_mode == "asset_type"
                else "四笔钱最优配置方案"
            )
            scope_note = (
                "（保障类持仓不计入投资规划可配置总资产）"
                if result.view_mode == "asset_type"
                else ""
            )
            lines = [
                f"基于客户{risk_name}风险画像，"
                f"{'可配置' if result.view_mode == 'asset_type' else ''}"
                f"总资产{result.total_assets:,.0f}元{scope_note}"
                f"{self._addon_holding_clause(result.idle_cash)}，",
                f"采用「{strategy}」策略，生成{plan_label}：",
            ]
        for item in result.category_summary:
            adj = item["adjust_amount"]
            direction = "增配" if adj > 0 else ("减配" if adj < 0 else "维持")
            band_ok = "✓ 落在模型区间" if item["in_band"] else "△ 取区间次优解"
            lines.append(
                f"· {item['category_name']}：目标占比{item['target_ratio']:.1%}，"
                f"当前{item['current_ratio']:.1%}→调整后{item['final_ratio']:.1%}，"
                f"{direction}{abs(adj):,.0f}元，{band_ok}"
            )
        return "\n".join(lines)

    @staticmethod
    def _mode_label(mode: str) -> str:
        labels = {
            "smart_one_click": "智能一键",
            "manual_tweak": "人工微调",
            "manual_product_edit": "人工配置",
            "flag_personalized": "个性化智能配仓",
            "optimal_personalized": "个性化智能配仓（新）",
        }
        return labels.get(mode, mode)

    @staticmethod
    def _describe_solver_strategy() -> str:
        solver = load_four_money_rule().get("solver", {})
        parts: list[str] = []
        if solver.get("minimize_cash_movement", True):
            parts.append("大类最小资金异动")
        else:
            parts.append("大类向模型目标靠拢")
        if solver.get("consolidate_category_rebalance", False):
            parts.append("类内单产品集中调仓")
        elif solver.get("prefer_existing_holdings", True):
            parts.append("类内优先存量比例")
        else:
            parts.append("类内产品均分")
        parts.append("仅已有持仓产品参与调仓")
        return "、".join(parts)

    def _build_over_under_reason(
        self, result: RebalanceResult, names: dict[str, str]
    ) -> str:
        over, under = [], []
        for item in result.category_summary:
            adj = item["adjust_amount"]
            if adj > 100:
                under.append(f"{item['category_name']}（低配{abs(item['current_ratio'] - item['target_ratio']):.1%}）")
            elif adj < -100:
                over.append(f"{item['category_name']}（超配{abs(item['current_ratio'] - item['target_ratio']):.1%}）")

        parts = []
        if over:
            parts.append(f"超配项：{'、'.join(over)}，建议减配回归模型区间。")
        if under:
            parts.append(f"低配项：{'、'.join(under)}，建议增配至目标水平。")
        if not parts:
            parts.append("当前四笔钱配比整体接近目标模型，微调幅度较小。")
        return " ".join(parts)

    def _build_customer_fit(
        self, customer: dict[str, Any], result: RebalanceResult, risk_name: str
    ) -> str:
        horizon = customer.get("invest_horizon_years", 5)
        age = customer.get("age", "")
        notes = customer.get("notes", "")
        return (
            f"{customer['name']}（{age}岁，{risk_name}）投资期限{horizon}年。"
            f"{notes}。"
            f"方案在保障{horizon}年投资目标的前提下，"
            f"{'生钱的钱占比较高，匹配长期增值需求' if result.risk_profile in ('growth', 'aggressive') else ''}"
            f"{'保值的钱为主，符合稳健偏好' if result.risk_profile in ('conservative', 'prudent') else ''}"
            f"{'四笔钱均衡配置，兼顾流动性与收益' if result.risk_profile == 'balanced' else ''}。"
        )

    def _build_manager_summary(
        self,
        result: RebalanceResult,
        customer: dict[str, Any],
        names: dict[str, str],
        risk_name: str,
    ) -> str:
        buy_total = sum(d.delta_amount for d in result.product_deltas if d.delta_amount > 0)
        sell_total = sum(abs(d.delta_amount) for d in result.product_deltas if d.delta_amount < 0)
        active = [d for d in result.product_deltas if abs(d.delta_amount) >= 100]

        lines = [
            f"【理财经理摘要】{customer['name']} | {risk_name} | 总资产{result.total_assets:,.0f}元",
            f"调仓模式：{self._mode_label(result.mode)}",
            f"预计买入{buy_total:,.0f}元，卖出{sell_total:,.0f}元，涉及{len(active)}只产品。",
        ]
        if result.validation_notes:
            lines.append(f"校验：{'; '.join(result.validation_notes)}")
        return "\n".join(lines)

    def _build_client_script(
        self,
        result: RebalanceResult,
        customer: dict[str, Any],
        names: dict[str, str],
        risk_name: str,
    ) -> str:
        lines = [
            f"{customer['name']}您好，",
            f"根据您{risk_name}的风险偏好，我们为您优化了四笔钱资产配置方案：",
        ]
        for item in result.category_summary:
            if abs(item["adjust_amount"]) >= 100:
                action = "增加" if item["adjust_amount"] > 0 else "减少"
                lines.append(
                    f"· {item['category_name']}：建议{action}{abs(item['adjust_amount']):,.0f}元"
                )
        lines.append("调整后配置更贴合您的理财目标，如有疑问欢迎随时沟通。")
        return "\n".join(lines)
