---
name: flag-personalized-allocation
description: >-
  Operates the weathmanage flag-driven personalized allocation engine
  (FlagDrivenSolver, mode flag_personalized): health-flag scenarios,
  per-class merge rules, normalization, and independence from smart_one_click.
  Use when implementing or debugging 个性化智能配仓, 健康标志配仓,
  flag_personalized, FlagDrivenSolver, or flag-driven rebalance logic.
---

# 个性化配仓引擎（健康标志驱动）

## 业务能力

**个性化智能配仓**：仅 **投资规划** 视图下，根据客户**业绩/风险健康标志**（非结构标志）计算四类资产目标，再分配到底层产品。与 **全账户一键 `smart_one_click` 完全独立**，共用产品层分摊与人工二次微调，**不共用** `_solve_category_targets` / `_solve_allocate_with_limit_freeze`。

| 模块 | 路径 |
|------|------|
| 大类求解器 | `asset_allocation/flag_driven_solver.py` |
| 引擎接入 | `asset_allocation/auto_rebalance_engine.py` → `mode == "flag_personalized"` |
| 标志来源 | `core/wealth_journey_service.py` → `build_diagnosis()` |
| API | `POST /api/allocation/auto_rebalance` + `mode: "flag_personalized"` |
| 前端 | `frontend/smart_allocation.html` → `#btnPersonalizedOptimize` |
| 测试 | `tests/test_flag_driven.py` |

与一键配仓 Skill 关系：规则阈值见 `four-money-rules`；产品分配/结果字段见 `smart-allocation-engine`。**改个性化算法只动 `FlagDrivenSolver` 与引擎 `flag_personalized` 分支，禁止改 `smart_one_click` 求解路径。**

---

## 入口与触发

| 条件 | 行为 |
|------|------|
| 规划类型 ≠ 投资规划 | 前端隐藏按钮；API 400 |
| 无标志，或仅有 `four_money_mismatch` | Toast/API：**「财富健康，请用全账户一键配仓」**，不执行 |
| 含任一业绩/风险标志 | `mode=flag_personalized`，服务端从诊断重新取标志（不信任前端传 flag） |

有效标志 code（`PERFORMANCE_FLAG_CODES`）：

| code | 展示名 | 触发（诊断） |
|------|--------|--------------|
| `return_below_expected` | 收益不达预期 | 年化收益 < 模型预期 − 0.5% |
| `return_above_expected` | 收益超预期 | 年化收益 > 模型预期 + 3% |
| `principal_loss_exceeded` | 本金损失超阈值 | 浮亏 > 客户可承受 loss_pct |
| `volatility_exceeded` | 波动率超预期 | 波动率 > 模型预期 + 0.5% |

**排除**：`four_money_mismatch`（四笔钱/资产类型结构不合理）不参与个性化配仓，走一键配仓。

---

## 资产口径

- **四类资产**：`cash` / `fixed_income` / `equity` / `alternative`（`INVESTMENT_CARD_KEYS`）
- **阈值**：`resolve_asset_type_targets()` → `target`（基准）、`band[0]`（下限）、`band[1]`（上限）
- **现金总池**：活期 + 货币产品 + **可配置闲置资金**（求解器内 `_cash_pool` 将 idle 并入 cash 当前值）
- **现金有效下限**：`floor(cash) = max(benchmark, band_lo)` — **不得低于基准，不允许清零式突破基准**
- **总资产**：`sum(投资类产品持仓) + idle_cash`（保障类不计）

---

## 完整流水线

```
诊断 flags → 过滤有效标志 → 场景合并(per-class intent)
    → 另类让路(Phase B) → 裁剪 band
    → 归一化凑平(Phase D–F) → target_cat
    → _allocate_products_asset_type（复用一键产品层）
    → product_deltas / validation_notes
    → 人工微调走 apply_manual_product_targets（与一键相同）
```

---

## 单场景 per-class 规则

「不动」= 主动规则不触发；归一化阶段仍可作为**被动吸收差额**的类。

辅助动作：

- **降至基准** `_to_bench_down`：当前 > 基准 → 基准；否则保持
- **加至基准** `_to_bench_up`：当前 < 基准 → 基准；否则保持
- **降至上限** `_to_upper_cap`：当前 > 上限 → 上限；否则保持
- **调至上限** `bounds[cat]["hi"]`
- **调至下限** `bounds[cat]["lo"]`（现金用 floor）
- **带内保持** `_hold_in_band`

### 场景 1：收益不达预期 (`return_below_expected`)

| 类 | 目标 | 主动卖顺序 | 主动买顺序 |
|----|------|------------|------------|
| 现金 | 超基准 → 降至基准 | ① | — |
| 固收 | 超上限 → 降至上限 | ② | — |
| 权益 | 调至上限 | — | ① |
| 另类 | 带内保持（权益未到上限时不增配） | ③ | ②（仅权益触顶后） |

### 场景 2：收益超预期 (`return_above_expected`)

| 类 | 目标 | 主动卖 | 主动买 |
|----|------|--------|--------|
| 现金 | 低于基准 → 加至基准 | — | ① |
| 固收 | 调至上限 | — | ② |
| 权益 | 超基准 → 降至基准 | ① | — |
| 另类 | 调至下限 | ② | — |

### 场景 3：本金损失超阈值 (`principal_loss_exceeded`)

| 类 | 目标 | 主动卖 | 主动买 |
|----|------|--------|--------|
| 现金 | 低于基准 → 加至基准 | — | ② |
| 固收 | 调至上限 | — | ① |
| 权益 | 调至下限 | ① | — |
| 另类 | 超基准 → 降至基准 | ② | — |

### 场景 4：波动率超预期 (`volatility_exceeded`)

| 类 | 目标 | 主动卖 | 主动买 |
|----|------|--------|--------|
| 现金 | 低于基准 → 加至基准 | — | ① |
| 固收 | 低于基准 → 加至基准 | — | ② |
| 权益 | 超基准 → 降至基准 | ① | — |
| 另类 | 超基准 → 降至基准 | ② | — |

---

## 复合场景合并（per-class，非场景串联）

| 标志组合 | 策略 |
|----------|------|
| 收益低 + 本金亏 | **场景 3 全类** |
| 收益高 + 本金亏 | **场景 2 全类** |
| 收益低 + 波动高 | 现金/固收/另类：**场景 4**；权益：**折中** `bench + (upper−bench)×0.5`（`EQUITY_BLEND_RATIO=0.5`） |
| 本金亏 + 波动高 | **场景 3 全类**；权益/另类再取 `min(场景3, 场景4)` |
| 收益高 + 波动高 | **场景 2 全类**（与场景 4 在权益/现金方向一致） |
| 三标志及以上 | `_dominant_scenario`：本金亏 > 收益高 > 收益低 > 波动；再按上表 pairwise 处理 |

---

## 硬约束

1. 各大类 intent / 最终 `tgt` 裁剪在 `[floor, hi]` 内
2. **现金 floor = 基准**，全局凑平与卖出不得跌破
3. **另类永远为权益让路**（Phase B，见 [algorithm.md](algorithm.md)）
4. 所有调整以模型 band 为界；无法满足时写 `validation_notes` 次优解

---

## 归一化算法概要

目标：`Σ tgt[cat] = total`，且尽量贴近合并 intent。

| Phase | 名称 | 要点 |
|-------|------|------|
| A | 合并 intent | `_merged_intents` + 裁剪 band |
| B | 另类让路 | 权益未达 intent 时，从另类释放额度给权益；权益未触顶则另类不增 |
| C | 初始化 | `tgt = round(intent)` |
| D | 主动凑平 | `diff = total − Σtgt`；按 **dominant 场景** 的 BUY/SELL 顺序增/减 |
| E | 被动吸收 | 主动后仍有 diff：按 `PASSIVE_BUY/SELL_ORDER` 在 band 内吸收；标记「被动」的类优先语义 |
| F | 残差 | 仍有余额 → 归入 **固收**（band 通常最宽），并提示次优解 |

**主动顺序常量**（与代码一致）：

```text
SELL return_below:  cash → fixed_income → alternative
BUY  return_below:  equity → alternative
SELL return_above:  equity → alternative
BUY  return_above:  cash → fixed_income
SELL principal_loss / volatility: equity → alternative
BUY  principal_loss: fixed_income → cash
BUY  volatility: cash → fixed_income

PASSIVE_BUY:  fixed → cash → alt → equity
PASSIVE_SELL: alt → equity → fixed → cash  （cash 最后且受基准保护）
```

完整伪代码与符号定义见 **[algorithm.md](algorithm.md)**。

---

## 引擎接入（禁止与一键混用）

`AutoRebalanceEngine._rebalance_investment_planning` 中 `flag_personalized` 分支：

1. `FlagDrivenSolver().solve(current_cat, idle_cash, profile_targets, flag_codes)`
2. `_allocate_products_asset_type(target_cat=...)` — **直接传入求解器输出，不走** `_solve_category_targets`
3. `_build_deltas` → `_build_category_summary` → `_validate`
4. `RebalanceResult.mode = "flag_personalized"`

API（`routes.py`）：`flag_personalized` 时调用 `WealthJourneyService.build_diagnosis` 提取有效 flag_codes；空则 400。

---

## 修改指南

| 要改什么 | 改哪里 | 不要改 |
|----------|--------|--------|
| 单场景 per-class 规则 | `_scenario_intents` | `_solve_category_targets` |
| 复合合并 | `_merged_intents` / `_merge_below_vol` | `smart_one_click` 分支 |
| 归一化/让路 | `_normalize` / `_alternative_yields_equity` | `four_money_rule.yaml` solver 段 |
| 折中系数 | `EQUITY_BLEND_RATIO` | — |
| 入口文案 | 前端 toast + `FlagDrivenSolverError` | — |
| 产品触顶 spill | 仅当需 flag 专用 freeze 时扩展 flag 分支 | 一键 freeze 逻辑 |

---

## 验证检查清单

```
- [ ] 仅投资规划可触发；综合规划无按钮
- [ ] 无有效标志 / 仅 four_money_mismatch → 不执行，提示正确
- [ ] smart_one_click 行为与改前一致（回归 tests/test_allocation.py）
- [ ] flag 方案 validation_notes 含「个性化配仓依据：…」
- [ ] Σ category target（求解器输出）≈ total
- [ ] 现金类不低于基准
- [ ] pytest tests/test_flag_driven.py 通过
```

关键测试客户：`C20250602007`（本金亏）、`C20250602004`（收益低+结构标志）、`C20250602002`（健康，应拒绝）。

---

## 延伸阅读

- 归一化逐步伪代码：[algorithm.md](algorithm.md)
- 一键配仓与 product_deltas 解读：`../smart-allocation-engine/SKILL.md`
- 模型阈值链路：`../four-money-rules/SKILL.md`
