"""Aftercare plan builder — driven by aftercare_rule.yaml."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.config_loader import (
    get_category_names,
    get_demo_customer,
    load_aftercare_rule,
    get_risk_level_name,
)


class AftercarePlanBuilder:
    def __init__(self) -> None:
        self.rules = load_aftercare_rule()

    def build_plan(
        self,
        customer_id: str,
        rebalance_summary: list[dict[str, Any]] | None = None,
        advisor_name: str = "理财经理",
    ) -> dict[str, Any]:
        customer = get_demo_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer not found: {customer_id}")

        risk = customer["risk_profile"]
        visit_cfg = self.rules["visit_schedule"].get(risk, {})
        drawdown_cfg = self.rules["drawdown_alerts"].get(risk, {})
        triggers = self.rules.get("rebalance_triggers", {})
        templates = self.rules.get("communication_templates", {})

        now = datetime.now()
        initial_days = visit_cfg.get("initial_days", 7)
        regular_days = visit_cfg.get("regular_interval_days", 30)
        review_days = visit_cfg.get("review_interval_days", 90)

        visit_schedule = {
            "initial_visit": (now + timedelta(days=initial_days)).strftime("%Y-%m-%d"),
            "next_regular_visit": (now + timedelta(days=regular_days)).strftime("%Y-%m-%d"),
            "next_review": (now + timedelta(days=review_days)).strftime("%Y-%m-%d"),
            "initial_days": initial_days,
            "regular_interval_days": regular_days,
            "review_interval_days": review_days,
        }

        drawdown_thresholds = {
            "warning": drawdown_cfg.get("warning_threshold", -0.05),
            "critical": drawdown_cfg.get("critical_threshold", -0.10),
            "warning_pct": f"{drawdown_cfg.get('warning_threshold', -0.05):.1%}",
            "critical_pct": f"{drawdown_cfg.get('critical_threshold', -0.10):.1%}",
        }

        rebalance_triggers = {
            "category_deviation_threshold": triggers.get("category_deviation_threshold", 0.08),
            "idle_cash_ratio_threshold": triggers.get("idle_cash_ratio_threshold", 0.20),
        }

        # 生成沟通话术
        scripts = self._generate_scripts(
            customer, rebalance_summary, templates, advisor_name, visit_schedule
        )

        return {
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "risk_profile": risk,
            "visit_schedule": visit_schedule,
            "drawdown_thresholds": drawdown_thresholds,
            "rebalance_triggers": rebalance_triggers,
            "communication_scripts": scripts,
            "export_formats": self.rules.get("export", {}).get("formats", ["text"]),
        }

    def _generate_scripts(
        self,
        customer: dict[str, Any],
        summary: list[dict[str, Any]] | None,
        templates: dict[str, Any],
        advisor_name: str,
        visit_schedule: dict[str, Any],
    ) -> list[dict[str, str]]:
        scripts = []
        risk_profile_name = get_risk_level_name(customer["risk_profile"])

        ratios = {s["category"]: s.get("final_ratio", s.get("target_ratio", 0)) for s in (summary or [])}

        # 初始回访话术
        init_tpl = templates.get("initial_visit", {}).get("template", "")
        if init_tpl:
            scripts.append({
                "id": "initial_visit",
                "title": templates["initial_visit"].get("title", "配置落地回访"),
                "content": init_tpl.format(
                    customer_name=customer["name"],
                    advisor_name=advisor_name,
                    age=customer.get("age", ""),
                    risk_profile_name=risk_profile_name,
                    spend_ratio=f"{ratios.get('spend', 0):.1%}",
                    preserve_ratio=f"{ratios.get('preserve', 0):.1%}",
                    grow_ratio=f"{ratios.get('grow', 0):.1%}",
                    protect_ratio=f"{ratios.get('protect', 0):.1%}",
                    next_visit_date=visit_schedule["next_regular_visit"],
                ).strip(),
            })

        # 偏差提醒话术（针对超配/低配项）
        if summary:
            names = get_category_names()
            for item in summary:
                if not item.get("in_band", True):
                    dev = abs(item.get("final_ratio", 0) - item.get("target_ratio", 0))
                    tpl = templates.get("deviation_alert", {}).get("template", "")
                    if tpl:
                        scripts.append({
                            "id": f"deviation_{item['category']}",
                            "title": f"{names.get(item['category'], '')}偏差提醒",
                            "content": tpl.format(
                                customer_name=customer["name"],
                                category_name=names.get(item["category"], item["category"]),
                                deviation_pct=f"{dev:.1%}",
                                action_suggestion="进行再平衡调整" if dev > 0.05 else "持续关注",
                            ).strip(),
                        })

        # 再平衡建议
        reb_tpl = templates.get("rebalance_suggest", {}).get("template", "")
        if reb_tpl and summary:
            for item in summary:
                adj = item.get("adjust_amount", 0)
                if abs(adj) > 100:
                    scripts.append({
                        "id": f"rebalance_{item['category']}",
                        "title": f"{item['category_name']}再平衡建议",
                        "content": reb_tpl.format(
                            customer_name=customer["name"],
                            category_name=item["category_name"],
                            adjust_amount=f"{abs(adj):,.0f}",
                        ).strip(),
                    })

        return scripts
