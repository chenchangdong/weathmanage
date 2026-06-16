# 个性化智能配仓（新）算法说明

实现：`asset_allocation/auto_rebalance_engine.py` → `mode == "optimal_personalized"`  
主 Skill：[SKILL.md](SKILL.md)

---

## 设计意图

把 **一键配仓的大类求解** 与 **标志个性化的产品落实 UX** 组合：

```text
大类层：复用 smart_one_click 的 _solve_category_targets（最小异动、band 约束）
产品层：复用 flag_personalized 的 hold-first + flag_category_suggest 分步落实
```

**不**在首次响应调用 `_allocate_products_asset_type` 或 `_solve_allocate_with_limit_freeze`。

---

## 与相邻 mode 的分叉点

```text
_rebalance_investment_planning(...)
│
├─ optimal_personalized / flag_personalized
│     ├─ 算 target_cat（算法不同）
│     ├─ product_targets = invest_holdings
│     ├─ product_deltas = 全 hold
│     └─ return（早退）
│
└─ smart_one_click / manual_tweak
      ├─ target_cat = _solve_category_targets 或单类版
      ├─ _solve_allocate_with_limit_freeze → 产品一次配满
      └─ return
```

---

## Step 1：准备（与一键相同）

| 步骤 | 说明 |
|------|------|
| invest_holdings | 排除保障类 |
| total | sum(invest_holdings) + idle_cash |
| current_cat | 按 asset_type 聚合 |
| display_current | `_current_with_addon(current_cat, idle_cash, "cash")` |
| profile_targets | `resolve_asset_type_targets(..., loss_key)` |

---

## Step 2：大类求解 `_solve_category_targets`

**与全账户 `smart_one_click` 完全相同的调用：**

```python
target_cat = self._solve_category_targets(
    total=total,
    current_cat=display_current,
    profile_targets=profile_targets,
    locked=locked,
    overrides=overrides,
    target_category=None,
    categories=invest_cats,
)
```

策略由 `four_money_rule.yaml` → `solver` 驱动（`minimize_cash_movement`、`fallback_strategy` 等）。  
详见 `../smart-allocation-engine/algorithm.md`。

**与 flag_personalized 的差异：** 不读 `flag_codes`，不调用 `FlagDrivenSolver`。

---

## Step 3：产品层 hold-only

```python
product_targets = dict(invest_holdings)
product_deltas = self._build_deltas(
    invest_holdings, product_targets, {}, use_asset_type_key=True
)
```

所有产品 `delta_amount ≈ 0`，`action = hold`。

---

## Step 4：汇总与校验

```python
category_summary = self._build_category_summary(
    total, display_current, target_cat, profile_targets, ...
)
val_notes = self._validate(total, target_cat, profile_targets, product_deltas, ...)
notes = ["个性化智能配仓（新）：依据全账户最优比例生成大类处方"] + val_notes
```

若全 hold 且无其他提示，追加：**「大类调仓建议已生成，产品层待落实」**。

---

## Step 5：用户逐类落实（前端 + API）

理财经理在配置页对某大类点击 **「一键自动调仓」**：

```text
POST /allocation/flag_category_suggest
  → engine.suggest_flag_category_products(...)
  → _allocate_products_asset_type(only_category=该类)
  → 返回该类 product_deltas 参考值（不改动大类处方）
```

与 `flag_personalized` **共用** `suggest_flag_category_products`；大类 `category_targets` 冻结在 `PlanEditor._categoryPrescription`。

手工改产品后：

```text
POST /allocation/manual_adjust
  → mode 变为 manual_product_edit
  → categoryPrescription 仍保留在 sessionStorage
```

---

## 口径对照表

| 模式 | 大类求解 | idle 并入 | 首次产品层 |
|------|----------|-----------|------------|
| smart_one_click | `_solve_category_targets` + freeze | cash | 已分配 |
| flag_personalized | FlagDrivenSolver | Solver 内 `_cash_pool` | hold |
| **optimal_personalized** | `_solve_category_targets` | `_current_with_addon` → cash | hold |

---

## 不变式

1. `Σ target_cat[c] ≈ total`
2. 首次 `product_deltas` 全部 hold
3. `category_summary[].adjust_amount` 反映大类处方（与一键同口径）
4. 逐类 suggest 后，该类产品目标加总应 ≈ 该类 `target_cat[category]`
5. 改 optimal 分支不得改变 `smart_one_click` 在 `if mode in (...)` **之后**的代码路径

---

## 回归 guard

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance -v
pytest tests/test_flag_driven.py::TestFlagPersonalizedRebalance::test_smart_one_click_unchanged -v
```

`test_optimal_differs_from_flag_when_both_available`：有标志客户上，optimal 与 flag 的 `category_summary.target_amount` 应不同。
