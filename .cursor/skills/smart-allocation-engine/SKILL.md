---
name: smart-allocation-engine
description: >-
  Operates the weathmanage smart allocation engine: one-click optimal rebalance,
  single-category optimize, manual tweak, product-level edits, and smart
  allocation page UX (toolbar, loss_key, wealth journey). Explains in-band vs
  suboptimal results, over/under allocation, and rebalance output fields. Use
  when implementing or debugging 一键智能最优配置, 单类智能优化, auto_rebalance,
  allocation results, product_deltas, smart_allocation.html, or 次优解.
---

# 智能配仓引擎

## 一句话

在客户所选**资产配置模型**的各大类占比区间内，用**尽量少的买卖**把持仓调到合理位置，并拆到具体产品。

## 先选路径：三种配仓方式

| 用户操作 | mode | 大类怎么算 | 适用 |
|----------|------|------------|------|
| 全账户一键 / 单类优化 / 人工微调 | `smart_one_click` / `manual_tweak` | `_solve_category_targets` | 默认；结构健康或综合规划 |
| 个性化智能配仓 | `flag_personalized` | `FlagDrivenSolver`（**独立算法**） | 仅投资规划 + 有业绩/风险标志 |
| 方案里改产品金额 | `manual_product_edit` | 不重算大类，只校验区间 | 手工配置 / 编辑器 |

个性化配仓见 `flag-personalized-allocation` Skill。**禁止**在 flag 路径里调用 `_solve_category_targets`。

## 规划类型：卡片长什么样

| 规划类型 | view_mode | 大类维度 | 引擎 categories |
|----------|-----------|----------|-----------------|
| **投资规划**（主路径） | `asset_type` | 现金 / 固收 / 权益 / 另类 | `INVESTMENT_CARD_KEYS` |
| **综合规划** | `four_money` | 四笔钱 spend/preserve/grow/protect | `four_money_rule.categories` |

同一套引擎，通过 `product_category` 分支；阈值分别来自 `resolve_asset_type_targets` 与 `resolve_profile_targets`。

## 模型怎么定：风险 vs 用户指派

默认：`客户 risk_profile` → `portfolio_mapping` → `loss_key` → 模型 P1/P2-x。

用户可在智能资配页工具栏 **第三行** 切换 **投资组合偏好 / 预期年化收益**（Tab 互斥）并选档位 → 请求带 `loss_key`，覆盖默认映射，**只换模型阈值，不换求解步骤**。下拉宽度与客户/规划类型一致（220px）；每次进入页面恢复该客户 risk 默认档位。

```text
resolve_*_targets(product_category, risk_profile, loss_key?)
  → targets: 每类 { target, band[下,上] }
  → model: model_code, loss_label, expect_annual_return ...
```

## 算法总览（易懂版）

```text
① 算总资产 total = 持仓合计 + idle_cash（投资规划排除保障类）
② 查模型 → 每大类有：基准占比、区间 [下限, 上限]
③ 大类求解 → 每类目标金额（见 algorithm.md）
④ [可选] 产品触顶 → 冻结该类 → 其余类重算（最多 10 轮）
⑤ 产品分配 → 大类目标拆到各产品（consolidate / spill）
⑥ 校验 → validation_notes、category_summary、product_deltas
```

**核心原则（给理财经理的说法）：**

1. **已在区间内 → 尽量不动**（`minimize_cash_movement`）
2. **越界了 → 按策略拉回**（默认 `band_midpoint`，单类超配减到**基准**）
3. **产品只动有持仓的**；0 持仓新产品只能手工加
4. **大类目标之和 = 总资产**（归一化保证）

逐步说明与伪代码 → **[algorithm.md](algorithm.md)**

## 业务概念（看哪个字段）

| 说法 | 含义 | 字段 |
|------|------|------|
| 在区间内 | 方案占比落在模型 band 内 | `category_summary[].in_band` |
| 次优解 | 触产品限额或区间塞不下意图 | `validation_notes` |
| 超配/低配 | 相对**基准**建议减/增 | `adjust_amount` 正/负 |
| 最小异动 | 在 band 内保持现仓 | solver 配置 |
| 类内集中 | 一只主产品承接增减 | `consolidate_category_rebalance` |

`in_band` 与 `adjust_amount` 是不同维度，不要混用。

## 配仓模式（mode）与 API

| mode | 场景 | 关键参数 |
|------|------|----------|
| `smart_one_click` | 全账户或单类 | `target_category` 可选 |
| `manual_tweak` | 锁定大类 + 指定金额 | `locked_categories`, `manual_overrides` |
| `flag_personalized` | 标志驱动 | 服务端从诊断取 flag，需 `loss_key` 等同左 |
| `manual_product_edit` | 产品级手调 | `manual_adjust` API |

```json
POST /api/allocation/auto_rebalance
{
  "customer_id": "C20250602001",
  "mode": "smart_one_click",
  "product_category": "投资规划",
  "loss_key": "loss_6pct",
  "idle_cash": 500000
}
```

### 单类智能优化（重要）

- 只调 `target_category` 那一类，**其余大类冻结在当前持仓**
- 超配 → 减到**基准**（不是 band 中点）
- 低配 → 用 `fallback_strategy`（默认 band 中点）
- 未配置的 idle 会在 `validation_notes` 说明

## 产品层规则（大类 → 产品）

1. 智能配仓**只在已有持仓产品**间分配（`_held_products`）
2. `consolidate=true`：优先级最高的一只产品承接，触 min/max 时 spill 到下一只
3. `liquidate_below_min=true`：可卖到 0
4. 产品目标加总应等于大类目标（测试不变式）

## 核心模块

| 模块 | 路径 |
|------|------|
| 引擎 | `asset_allocation/auto_rebalance_engine.py` |
| 规则注入 | `core/allocation_config_service.py` |
| 标志求解（独立） | `asset_allocation/flag_driven_solver.py` |
| API | `api/routes.py` |
| 前端 | `frontend/smart_allocation.html`, `js/plan_editor.js`, `js/model_selector.js`, `js/advisor_chat.js` |

配置从哪改 → `four-money-rules` Skill。

## 智能资配页工具栏（投资规划）

```text
选择客户 + 财富健康标志（右列对齐）
规划类型 + 追加持仓（右列对齐）
投资组合偏好 | 预期年化收益 + 模型下拉
```

- 标志：`GET /api/wealth/diagnosis` → `#overviewHealthFlags`
- 顾问侧栏：`data-advisor-dock`，默认展开，跨页保留对话与流式续传
- 财富旅程：财富盘点 → 资产诊断 → 智能资配（见 scenarios 场景 1、11）

## 结果怎么读

**category_summary**：`current_ratio`（现况）→ `final_ratio`（方案）→ `band`（模型区间）→ `in_band`

**product_deltas**：`action` buy/sell/hold，`delta_amount`，`limit_hit` / `limit_side`

**validation_notes**：向经理解读次优、单类缺口、产品触顶冻结等。

## 排查表

| 现象 | 先查 | 常见原因 |
|------|------|----------|
| 0 持仓产品不在方案里 | `product_deltas` | 设计如此；需手工添加 |
| 单类优化后总资产不满配 | `validation_notes` | 其他大类冻结 |
| 超配没减到预期 | mode + solver | 单类减到基准；全账户看 fallback |
| 产品触下限卖不动 | `limit_hit` | min_amount |
| 阈值不对 | resolve API + loss_key | 改配置或页面模型选择 |
| 个性化与一键结果混淆 | `mode` | 两套大类求解器 |

```bash
pytest tests/test_allocation.py -v
pytest tests/test_flag_driven.py -v
python demo_test.py --customer C20250602001
```

## 与其他 Skill 的边界

| Skill | 关系 |
|-------|------|
| `four-money-rules` | 阈值、模型、产品从哪来 |
| `flag-personalized-allocation` | 标志驱动大类求解（独立）；演示场景见其 `scenarios.md` |
| ExplainAgent | 规则解读，非 LLM 配仓 |

## 验证清单

```
- [ ] resolve 阈值与 risk / loss_key 一致
- [ ] category_summary 各大类 in_band 符合预期
- [ ] product_deltas 仅含应调仓产品
- [ ] 产品目标加总 ≈ 大类目标
- [ ] validation_notes 已向经理解读（有次优时）
- [ ] pytest tests/test_allocation.py 通过
```

典型场景 → [scenarios.md](scenarios.md)  
一键算法细节 → [algorithm.md](algorithm.md)
