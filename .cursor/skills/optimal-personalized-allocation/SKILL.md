---
name: optimal-personalized-allocation
description: >-
  Operates the weathmanage optimal-prescription allocation mode
  (optimal_personalized): one-click _solve_category_targets for category
  targets, hold-only product layer, prescription orchestration UI shared with
  flag_personalized. Use when implementing or debugging 个性化智能配仓（新）,
  optimal_personalized, prescription + one-click hybrid, or comparing it with
  flag_personalized and smart_one_click.
---

# 个性化智能配仓（新）

## 一句话

**大类目标**用全账户一键最优算法（`_solve_category_targets`），**产品落实**与旧版个性化相同（先 hold-only，再逐类一键自动调仓）。适合「财富健康、无标志」但仍希望理财经理分步落实产品的场景。

## 三种配仓方式对照

```text
smart_one_click           →  大类最优 + 产品一次配满
flag_personalized         →  标志驱动大类 + 产品分步落实
optimal_personalized（新） →  大类最优 + 产品分步落实   ← 本 Skill
```

| 维度 | 个性化（旧）`flag_personalized` | 个性化（新）`optimal_personalized` | 全账户一键 `smart_one_click` |
|------|--------------------------------|-------------------------------------|------------------------------|
| 大类算法 | `FlagDrivenSolver` | `_solve_category_targets` | `_solve_category_targets` |
| 前置条件 | 投资规划 + 有效财富健康标志 | **仅投资规划**（无标志要求） | 投资/综合规划 |
| 首次 product_deltas | 全部 hold | 全部 hold | 已有买卖建议 |
| 配置页 UI | 大类处方 + 产品落实 | **相同** | 可编辑方案卡片 |
| 逐类填产品 | `flag_category_suggest` | **相同** | 不需要 |

**改本模式算法：** 只动 `auto_rebalance_engine` 中 `optimal_personalized` 分支 + 前端 `PRESCRIPTION_MODES`；**禁止**改 `FlagDrivenSolver` 或 `smart_one_click` 主路径。

## 什么时候能点「个性化智能配仓（新）」

| 条件 | 结果 |
|------|------|
| 规划类型 ≠ 投资规划 | `#btnOptimalPersonalized` 隐藏 |
| 规划类型 = 投资规划 | 按钮可见；**不要求**财富健康标志 |
| 财富健康（无有效标志） | 可用本模式；旧版「个性化智能配仓」仍会被拒绝 |

与旧版个性化共用配置页（`smart_allocation_setup.html`）与方案落实页（`smart_allocation.html` + `plan_editor.js`）。

## 端到端流程

```text
Setup（KYC + 规划类型 + loss_key + 追加持仓）
  → smart_allocation.html 资产检视
  → #btnOptimalPersonalized
  → POST auto_rebalance { mode: "optimal_personalized" }
  → 引擎：_solve_category_targets → category_summary（含 adjust_amount）
  → product_deltas 全 hold（产品层待落实）
  → cacheCategoryPrescription → renderPersonalizedPlanCards
  → 逐类「一键自动调仓」→ POST flag_category_suggest
  → 手工微调 → manual_adjust（mode → manual_product_edit，处方缓存保留）
```

逐步算法 → **[algorithm.md](algorithm.md)**  
演示客户与 curl → **[scenarios.md](scenarios.md)**

## 引擎分支（投资规划）

`auto_rebalance_engine._rebalance_investment_planning`：

```text
if mode in ("flag_personalized", "optimal_personalized"):
    if mode == "flag_personalized":
        target_cat ← FlagDrivenSolver.solve(...)
    else:
        target_cat ← _solve_category_targets(...)   # 与 smart_one_click 全账户相同入参
    product_targets ← 当前 invest_holdings（hold-only）
    product_deltas ← 全 hold
    return RebalanceResult(mode=mode, ...)
# 以下 smart_one_click / manual_tweak 路径不变
```

**关键：** `optimal_personalized` **只借用** `_solve_category_targets` 算大类，**不调用** `_solve_allocate_with_limit_freeze`，因此首次响应不含产品买卖。

## 追加持仓口径

与一键、旧版个性化展示一致：

| 层级 | idle 处理 |
|------|-----------|
| `_solve_category_targets` 输入 current | `display_current = _current_with_addon(..., "cash")` |
| `category_summary` 活钱类 current | 含 idle |
| `RebalanceResult.idle_cash` | 单独返回 |

## 前端：`PRESCRIPTION_MODES`

`plan_editor.js` 将两种个性化 mode 统一为「处方落实」：

```javascript
PRESCRIPTION_MODES: ['flag_personalized', 'optimal_personalized']
isPrescriptionMode(mode)  // 缓存处方、渲染个性化卡片、一键还原配仓等
```

| 模块 | 路径 |
|------|------|
| 按钮 | `#btnOptimalPersonalized`（`smart_allocation.html`） |
| 入口逻辑 | `runPrescriptionRebalance('optimal_personalized', ...)` |
| 上下文面板 | `renderPersonalizedContextPanel` → 「依据全账户最优比例生成大类处方」 |
| 处方缓存 | `cacheCategoryPrescription` / `categoryPrescription` in sessionStorage |
| 逐类建议 | `applyCategorySuggest` → `POST /allocation/flag_category_suggest`（与旧版共用） |

**缓存隔离：** 两种个性化 mode 的已保存处方互不混用；切换 mode 时丢弃不匹配缓存。

## API

```json
POST /api/allocation/auto_rebalance
{
  "customer_id": "C20250602002",
  "mode": "optimal_personalized",
  "product_category": "投资规划",
  "loss_key": "loss_6pct",
  "idle_cash": 0
}
```

| 校验 | 行为 |
|------|------|
| `product_category != 投资规划` | 400「个性化智能配仓仅支持投资规划」 |
| 不要求 diagnosis flags | 与 `flag_personalized` 不同 |

逐类产品建议（共用）：

```json
POST /api/allocation/flag_category_suggest
{ "customer_id", "category", "category_targets", "baseline_product_targets", "idle_cash" }
```

## 改什么去哪个文件

| 要改 | 文件 | 不要改 |
|------|------|--------|
| 大类最优策略 | `four_money_rule.yaml` solver + `_solve_category_targets` | `FlagDrivenSolver` |
| 新模式 hold-only 行为 | `auto_rebalance_engine` optimal 分支 | `smart_one_click` freeze 路径 |
| 按钮 / 文案 | `smart_allocation.html`, `plan_editor.js` | — |
| 配置解读 | `agent_core/explain_agent.py` optimal 分支 | — |
| 测试 | `tests/test_flag_driven.py::TestOptimalPersonalizedRebalance` | 现有 flag / one-click 用例 |

## 排查

| 现象 | 查什么 |
|------|--------|
| 与全账户一键大类不一致 | 对比 `category_targets`；应相同 solver 入参（total、display_current、profile_targets） |
| 与旧版个性化大类相同 | 不应相同（标志客户上 flag ≠ optimal）；确认 mode |
| 首次就有产品买卖 | mode 误为 `smart_one_click` |
| 按钮不可见 | `getProductCategory()` 是否为投资规划 |
| 健康客户旧版能点？ | 旧版需 flags；新版不需要 |
| 还原后按钮不变回自动调仓 | `_manualDeltaEditedCategories` 须在 `onUpdated` 前清除 |

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance -v
pytest tests/test_flag_driven.py::TestFlagPersonalizedRebalance::test_smart_one_click_unchanged -v
```

## 验证清单

```
- [ ] 仅投资规划可触发；综合规划 400
- [ ] 无财富健康标志也可成功（如 C20250602002）
- [ ] mode=optimal_personalized；product_deltas 首次全 hold
- [ ] validation_notes 含「个性化智能配仓（新）」
- [ ] 与 flag_personalized 大类目标可不同（有标志客户）
- [ ] smart_one_click / flag_personalized 回归不变
- [ ] 处方缓存、一键自动调仓、一键还原配仓与旧版 UX 一致
```

## 与其他 Skill 的边界

| Skill | 关系 |
|-------|------|
| `smart-allocation-engine` | `_solve_category_targets` 算法细节、solver YAML |
| `flag-personalized-allocation` | 标志驱动大类；UI 层姊妹模式 |
| `four-money-rules` | 模型阈值、loss_key |

- 算法细节：[algorithm.md](algorithm.md)
- 演示场景：[scenarios.md](scenarios.md)
