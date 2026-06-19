#!/usr/bin/env python3
"""
demo_test.py — 构造银行真实客户测试数据，一键运行输出完整配置方案。

用法:
    python demo_test.py
    python demo_test.py --customer C20250602001
    python demo_test.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 确保项目根目录在 path 中
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent_core.explain_agent import ExplainAgent
from asset_allocation.auto_rebalance_engine import AutoRebalanceEngine
from core.asset_service import AssetOverviewService, overview_to_dict
from core.config_loader import load_customer_profile
from core.data_store import get_customer_holdings


def run_single(customer_id: str, verbose: bool = True) -> dict:
    """对单个客户运行完整流程：概览 → 配仓 → 解读。"""
    customer = None
    for c in load_customer_profile().get("demo_customers", []):
        if c["customer_id"] == customer_id:
            customer = c
            break
    if not customer:
        raise ValueError(f"Customer not found: {customer_id}")

    data = get_customer_holdings(customer_id)
    if not data:
        raise ValueError(f"No holdings: {customer_id}")

    if verbose:
        print("=" * 60)
        print(f"客户: {customer['name']} ({customer_id})")
        print(f"画像: {customer['risk_profile']} | {customer.get('notes', '')}")
        print("=" * 60)

    # 1. 资产概览
    overview_svc = AssetOverviewService()
    overview = overview_svc.build_overview(customer_id)
    overview_dict = overview_to_dict(overview)

    if verbose:
        print(f"\n【资产概览】总资产 {overview.total_assets:,.0f} 元")
        print(f"健康度: {overview.health_label} ({overview.health_level})")
        for cat in overview.categories:
            print(f"  {cat.category_name}: 当前 {cat.current_amount:,.0f} | 目标 {cat.target_amount:,.0f} | 偏差 {cat.deviation_pct}")

    # 2. 全账户智能配仓
    engine = AutoRebalanceEngine()
    result = engine.rebalance(
        customer_id=customer_id,
        holdings=data["holdings"],
        idle_cash=0.0,
        risk_profile=customer["risk_profile"],
        mode="smart_one_click",
    )

    if verbose:
        print(f"\n【智能配仓方案】模式: 智能一键")
        for s in result.category_summary:
            band = "✓" if s["in_band"] else "△"
            print(f"  {band} {s['category_name']}: 目标{s['target_ratio']:.1%} → 最终{s['final_ratio']:.1%} | 调整 {s['adjust_amount']:+,.0f}")
        print(f"\n  底层产品调仓:")
        for d in result.product_deltas:
            if abs(d.delta_amount) >= 1:
                print(f"    {d.product_name}: {d.current_amount:,.0f} → {d.target_amount:,.0f} ({d.delta_amount:+,.0f}) [{d.action}]")
        print(f"\n  校验: {'; '.join(result.validation_notes)}")

    # 3. AI 解读
    explain = ExplainAgent().generate(result)
    if verbose:
        print(f"\n【AI 配置解读】")
        print(explain["allocation_logic"])
        print(f"\n超配低配: {explain['over_under_reason']}")
        print(f"\n客户适配: {explain['customer_fit']}")

    return {
        "customer": customer,
        "overview": overview_dict,
        "rebalance": {
            "category_summary": result.category_summary,
            "product_deltas": [
                {"code": d.product_code, "name": d.product_name, "delta": d.delta_amount, "action": d.action}
                for d in result.product_deltas
            ],
            "validation_notes": result.validation_notes,
        },
        "explanation": explain,
    }


def main():
    parser = argparse.ArgumentParser(description="四笔钱智能配仓 Demo 自测")
    parser.add_argument("--customer", default="C20250602001", help="客户ID")
    parser.add_argument("--all", action="store_true", help="运行全部演示客户")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    customers = [c["customer_id"] for c in load_customer_profile().get("demo_customers", [])]
    targets = customers if args.all else [args.customer]

    results = []
    for cid in targets:
        try:
            r = run_single(cid, verbose=not args.json)
            results.append(r)
        except Exception as e:
            print(f"ERROR [{cid}]: {e}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(json.dumps(results if args.all else results[0], ensure_ascii=False, indent=2))

    if not args.json:
        print("\n" + "=" * 60)
        print(f"✓ 完成 {len(results)} 个客户的完整配置方案自测")
        print("=" * 60)


if __name__ == "__main__":
    main()
