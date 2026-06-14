# 一键配仓算法说明（smart_one_click）

实现文件：`asset_allocation/auto_rebalance_engine.py`  
配置开关：`config/four_money_rule.yaml` → `solver`

---

## 用一张图理解全流程

```text
  客户 + 持仓 + idle
         │
         ▼
  ┌──────────────────┐
  │ 解析模型阈值      │  resolve_*_targets(risk, loss_key?)
  │ 每类: 基准 + band │
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │ 大类求解          │  _solve_category_targets
  │ 每类目标金额      │
  └────────┬─────────┘
           ▼
  ┌──────────────────┐     产品触顶?
  │ 产品限额迭代      │◄─── _solve_allocate_with_limit_freeze
  │ 冻结类 + 重算     │     （最多 max_iterations 轮）
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │ 产品分配          │  _allocate_products / _allocate_products_asset_type
  │ consolidate/spill│
  └────────┬─────────┘
           ▼
     RebalanceResult
```

---

## 第 1 步：解析模型（不算配仓，只查表）

输入：规划类型、风险等级、可选 `loss_key`  
输出：每大类（或资产类型）：

```text
target = 基准占比（0~1 小数）
band   = [下限占比, 上限占比]
```

金额口径：`基准金额 = target × total`，`区间 = band × total`。

---

## 第 2 步：大类求解 `_solve_category_targets`

**目标：** 为每个大类算一个**目标金额**，尽量贴近模型，又尽量别乱动。

### 2.1 三种入口

| 情况 | 行为 |
|------|------|
| 有人工 `manual_overrides` | 直接用指定金额 |
| 大类在 `locked_categories` | 保持当前持仓 |
| 单类优化 `target_category` | 只动这一类（见下） |
| 全账户 | 所有未锁定类一起算 |

### 2.2 全账户 — 「最小异动」怎么理解

对每个**未锁定**大类：

```text
当前占比在 [下限, 上限] 内？ 
  是 → 目标 = 当前持仓（不动）
  否 → 目标 = fallback 落点（默认 band 中点，可配置 benchmark/band_low/band_high）
```

然后调用 `_normalize_targets`，保证：**所有大类目标金额之和 = total**。

### 2.3 单类优化 — 和全账户的区别

```text
其他大类：全部冻结 = 当前持仓（不参与归一化凑满 total）
目标类：
  在 band 内     → 保持现仓
  超配（>上限）  → 减到「基准」金额
  低配（<下限）  → 用 fallback（通常 band 中点）
  且不超过 total - 其他类持仓之和
```

所以单类优化后，**总资产可能配不满**，这是设计行为，不是 bug。

### 2.4 归一化 `_normalize_targets`（为什么需要）

全账户模式下，各「不动/回退」类加总可能 ≠ total。算法：

1. 算差额 `diff = total - Σ目标`
2. 把 diff **均分**到可调整大类，但每类不能超出 band
3. 若仍不平：由最后一类或 donor 类吸收残差（避免负目标）

**直觉：** 像把多出来或少了的钱，在还能动的类里分摊，且不能越界。

---

## 第 3 步：产品触顶迭代 `_solve_allocate_with_limit_freeze`

**问题：** 大类目标 100 万，但类内产品都触 max，实际只能落地 80 万。

**做法（循环，默认最多 10 轮）：**

```text
1. 按当前冻结状态，重算大类目标
2. 分配产品，汇总实际大类金额
3. 若某类 实际 < 目标 且非人工指定：
     → 冻结该类目标 = 实际可落地额
     → 回到步骤 1，让其他类重新分配
4. 直到无 shortfall 或无法进展
```

notes 会出现：「XX 因产品触顶，已冻结在可落地金额…」

---

## 第 4 步：产品分配 `_allocate_products`

大类目标金额 → 各产品目标金额。

### 模式 A：集中调仓 `consolidate=true`（默认）

```text
按 rebalance_priority 选一只「主产品」
  增配 → 尽量全给主产品，触 max → spill 到下一只
  减配 → 从主产品减，触 min → spill
```

### 模式 B：按现仓比例 `prefer_existing=true`

在无 consolidate 时，按各类产品现仓占比分摊，再 spill 处理限额。

### 共同约束

- **只考虑当前有持仓的产品**（智能配仓不自动买新产品）
- 单产品 clamp 到 [min_amount, max_amount]
- `liquidate_below_min` 允许卖到 0

---

## 配置项速查（改行为先改 YAML）

| 配置 | 效果 |
|------|------|
| `minimize_cash_movement` | true = 在 band 内不动 |
| `fallback_strategy` | 越界回退落点：benchmark / band_midpoint / band_low / band_high |
| `consolidate_category_rebalance` | 类内集中一只产品 |
| `prefer_existing_holdings` | 非集中时按现仓比例 |
| `liquidate_below_min` | 允许清仓式卖出 |
| `max_iterations` | 触顶冻结最大轮数 |

---

## 与个性化配仓的边界

| | smart_one_click | flag_personalized |
|--|-----------------|-------------------|
| 大类求解 | `_solve_category_targets` | `FlagDrivenSolver` |
| 触发 | 用户点一键 | 财富健康标志 |
| 产品层 | **共用** `_allocate_products_asset_type` | 同左 |

改一键大类逻辑 → 动 `auto_rebalance_engine` 求解段。  
改标志逻辑 → 只动 `flag_driven_solver.py`（见 flag Skill）。

---

## 口径注意：idle 与现金类

- **total** = 投资类持仓 + `idle_cash`（不含保障类）
- 一键路径：`idle_cash` 单独传入，**不**并入 cash 类 current 再求解（与 flag 求解器不同）
- 前端追加持仓：录入**万**，API 传**元**；会改变 total 与 idle
- 方案态「本次已配置闲置资金」来自 `product_deltas` 汇总，与 idle 字段口径可能不一致 → 排查时分开看

---

## 关键函数索引

| 函数 | 作用 |
|------|------|
| `_solve_category_targets` | 大类目标（含单类/全账户） |
| `_normalize_targets` | 凑平 total |
| `_solve_allocate_with_limit_freeze` | 触顶冻结循环 |
| `_allocate_products` | 四笔钱产品层 |
| `_allocate_products_asset_type` | 投资规划产品层 |
| `_allocate_category_consolidated` | 集中 + spill |
| `_clamp_product` | 单产品限额 |
